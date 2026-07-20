# Zion Stream - server local: extractie audio YouTube (yt-dlp) + releu audio HTTP
# pentru streamere Linkplay/Arylic + proxy de comenzi + auto-update din GitHub
# + logging cu upload optional in repo (token local in zion-config.json).
# Porneste cu: porneste-server.bat (sau automat, dupa instaleaza-autostart.bat)
import base64
import json
import logging
import os
import re
import shutil
import socket
import subprocess
import sys
import threading
import time
from logging.handlers import RotatingFileHandler

from flask import Flask, request, jsonify
import requests
import yt_dlp

VERSION = '1.3.0'
REPO = 'duchy-ctrl/zion-stream'
RAW = f'https://raw.githubusercontent.com/{REPO}/main'
FROZEN = bool(getattr(sys, 'frozen', False))

# cand rulam ca .exe (PyInstaller), fisierele impachetate sunt in _MEIPASS,
# iar folderul "de lucru" (config, loguri, update-uri) e langa .exe
if FROZEN:
    DIR = os.path.dirname(os.path.abspath(sys.executable))
    ASSET_DIR = sys._MEIPASS
else:
    DIR = os.path.dirname(os.path.abspath(__file__))
    ASSET_DIR = DIR

CONFIG = {}
try:
    with open(os.path.join(DIR, 'zion-config.json'), encoding='utf-8') as f:
        CONFIG = json.load(f)
except Exception:
    pass

# ---------- Auto-DJ: playlisturi predefinite + programare ----------
# Playlisturile sunt CAUTARI (nu linkuri fixe) ca sa nu moara niciodata:
# serverul ia mereu mixurile actuale de pe YouTube.
STATE_PATH = os.path.join(DIR, 'zion-state.json')
PRESETS = {
    'pool': {'name': '🏊 Deep House Piscină',
             'query': 'deep house sunset pool party mix 2025'},
    'chill': {'name': '🌅 Dolce Far Niente',
              'query': 'bossa nova jazz lounge chillout dinner mix'},
}
# activ = ultima intrare a carei ora a trecut (ordine crescatoare)
SCHEDULE = [
    {'from': '09:00', 'preset': 'pool'},
    {'from': '19:30', 'preset': 'chill'},
]
AUTODJ = {'enabled': False, 'ip': '', 'override_until': 0}


def load_state():
    try:
        with open(STATE_PATH, encoding='utf-8') as f:
            s = json.load(f)
        AUTODJ['enabled'] = bool(s.get('autodj_enabled', False))
        AUTODJ['ip'] = s.get('streamer_ip', '') or ''
    except Exception:
        pass


def save_state():
    try:
        with open(STATE_PATH, 'w', encoding='utf-8') as f:
            json.dump({'autodj_enabled': AUTODJ['enabled'],
                       'streamer_ip': AUTODJ['ip']}, f)
    except Exception:
        pass


# permite suprascrierea programului/presetelor din zion-config.json
if isinstance(CONFIG.get('presets'), dict):
    PRESETS.update(CONFIG['presets'])
if isinstance(CONFIG.get('schedule'), list) and CONFIG['schedule']:
    SCHEDULE = CONFIG['schedule']

# ---------- logging: fisier rotativ local + consola ----------
LOG_PATH = os.path.join(DIR, 'zion-log.txt')
logger = logging.getLogger('zion')
logger.setLevel(logging.INFO)
_fmt = logging.Formatter('%(asctime)s %(levelname)s %(message)s')
_fh = RotatingFileHandler(LOG_PATH, maxBytes=500_000, backupCount=1, encoding='utf-8')
_fh.setFormatter(_fmt)
_sh = logging.StreamHandler()
_sh.setFormatter(_fmt)
logger.addHandler(_fh)
logger.addHandler(_sh)
logging.getLogger('werkzeug').addHandler(_fh)

app = Flask(__name__)
BASE = {'quiet': True, 'no_warnings': True, 'skip_download': True, 'socket_timeout': 15}
VID_RE = re.compile(r'^[A-Za-z0-9_-]{11}$')
PID_RE = re.compile(r'^[A-Za-z0-9_-]{10,50}$')
IP_RE = re.compile(r'^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$')
CMD_RE = re.compile(r'^(getStatusEx|getPlayerStatus|setPlayerCmd:)')

AUDIO_CACHE = {}  # vid -> (url, expira_la, durata)
LAN_URL = ''


def lan_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return '127.0.0.1'


def ffmpeg_path():
    # bundle langa exe / in sursa, altfel din PATH
    exe = 'ffmpeg.exe' if os.name == 'nt' else 'ffmpeg'
    for c in (os.path.join(ASSET_DIR, exe), os.path.join(DIR, exe)):
        if os.path.exists(c):
            return c
    return shutil.which('ffmpeg') or ''


# ---------- auto-update din GitHub ----------
def _restart():
    logger.info('Repornesc serverul pentru update...')
    if FROZEN:
        os._exit(0)  # bat-ul de update reporneste exe-ul
    os.execv(sys.executable, [sys.executable, os.path.join(DIR, 'zion-server.py')])


def _update_from_source():
    r = requests.get(RAW + '/version.txt', timeout=10)
    if not r.ok:
        return
    latest = r.text.strip()
    if latest == VERSION:
        return
    logger.info(f'Update disponibil: {VERSION} -> {latest}. Descarc fisierele...')
    for name in ('zion-server.py', 'zion-stream.html'):
        fr = requests.get(f'{RAW}/{name}', timeout=20)
        fr.raise_for_status()
        with open(os.path.join(DIR, name), 'wb') as f:
            f.write(fr.content)
    logger.info('Fisiere actualizate.')
    _restart()


def _update_frozen():
    r = requests.get(f'https://api.github.com/repos/{REPO}/releases/latest', timeout=10)
    if not r.ok:
        return
    j = r.json()
    latest = (j.get('tag_name') or '').lstrip('v')
    if not latest or latest == VERSION:
        return
    asset = next((a for a in j.get('assets', []) if a['name'].endswith('.exe')), None)
    if not asset:
        return
    logger.info(f'Update disponibil: {VERSION} -> {latest}. Descarc {asset["name"]}...')
    new_exe = os.path.join(DIR, 'ZionStream-new.exe')
    with requests.get(asset['browser_download_url'], stream=True, timeout=120) as dl:
        dl.raise_for_status()
        with open(new_exe, 'wb') as f:
            for chunk in dl.iter_content(1024 * 256):
                f.write(chunk)
    cur = os.path.basename(sys.executable)
    bat = os.path.join(DIR, 'zion-update.bat')
    with open(bat, 'w') as f:
        f.write('@echo off\ntimeout /t 3 /nobreak >nul\n'
                f'move /y "ZionStream-new.exe" "{cur}" >nul\n'
                f'start "" "{cur}"\n')
    subprocess.Popen(['cmd', '/c', bat], cwd=DIR,
                     creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    logger.info('Pornesc schimbul de versiune si ies.')
    _restart()


def update_loop():
    time.sleep(10)
    while True:
        try:
            if CONFIG.get('auto_update', True):
                _update_frozen() if FROZEN else _update_from_source()
        except Exception as ex:
            logger.warning(f'Verificarea de update a esuat: {ex}')
        time.sleep(6 * 3600)


# ---------- upload loguri in GitHub (optional, token local) ----------
def logs_loop():
    token = CONFIG.get('github_token', '')
    if not token:
        logger.info('Fara github_token in zion-config.json - logurile raman doar locale.')
        return
    host = re.sub(r'[^A-Za-z0-9-]', '-', socket.gethostname()) or 'pc'
    api = f'https://api.github.com/repos/{REPO}/contents/logs/{host}.txt'
    headers = {'Authorization': 'Bearer ' + token,
               'Accept': 'application/vnd.github+json'}
    last = ''
    while True:
        time.sleep(CONFIG.get('log_upload_minutes', 10) * 60)
        try:
            with open(LOG_PATH, 'r', encoding='utf-8', errors='replace') as f:
                text = f.read()[-150_000:]
            if text == last:
                continue
            sha = None
            g = requests.get(api, headers=headers, timeout=15)
            if g.ok:
                sha = g.json().get('sha')
            body = {'message': f'loguri {host} ({time.strftime("%Y-%m-%d %H:%M")})',
                    'content': base64.b64encode(text.encode()).decode()}
            if sha:
                body['sha'] = sha
            p = requests.put(api, headers=headers, json=body, timeout=30)
            if p.ok:
                last = text
            else:
                logger.warning(f'Upload loguri esuat: HTTP {p.status_code}')
        except Exception as ex:
            logger.warning(f'Upload loguri esuat: {ex}')


def _self_update_ytdlp():
    if FROZEN:
        return  # in exe, yt-dlp e impachetat; se actualizeaza cu release-ul
    try:
        subprocess.run([sys.executable, '-m', 'pip', 'install', '--quiet',
                        '--upgrade', 'yt-dlp', 'requests'], timeout=300,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass


def audio_url(vid):
    now = time.time()
    hit = AUDIO_CACHE.get(vid)
    if hit and hit[1] > now:
        return hit[0], hit[2]
    with yt_dlp.YoutubeDL({**BASE, 'format': 'bestaudio[ext=m4a]/bestaudio/best'}) as ydl:
        info = ydl.extract_info(f'https://www.youtube.com/watch?v={vid}', download=False)
    url = info['url']
    dur = info.get('duration') or 0
    AUDIO_CACHE[vid] = (url, now + 3 * 3600, dur)  # linkurile googlevideo tin ~6h
    return url, dur


@app.after_request
def cors(r):
    r.headers['Access-Control-Allow-Origin'] = '*'
    return r


@app.errorhandler(Exception)
def on_error(ex):
    logger.exception('Eroare neasteptata')
    return jsonify(error=str(ex)), 500


@app.get('/')
def index():
    # varianta actualizata (descarcata de auto-update) are prioritate fata de cea impachetata
    for base in (DIR, ASSET_DIR):
        p = os.path.join(base, 'zion-stream.html')
        if os.path.exists(p):
            with open(p, encoding='utf-8') as f:
                return f.read()
    return 'Pune zion-stream.html in acelasi folder cu zion-server.py', 404


@app.get('/api/ping')
def ping():
    return jsonify(ok=True, server='zion-stream', lan=LAN_URL, ver=VERSION)


@app.get('/api/logs')
def logs_view():
    try:
        with open(LOG_PATH, 'r', encoding='utf-8', errors='replace') as f:
            return app.response_class(f.read()[-100_000:], mimetype='text/plain')
    except FileNotFoundError:
        return app.response_class('(fara loguri inca)', mimetype='text/plain')


@app.get('/api/search')
def search():
    q = request.args.get('q', '')
    if not q:
        return jsonify([])
    try:
        with yt_dlp.YoutubeDL({**BASE, 'extract_flat': True}) as ydl:
            info = ydl.extract_info(f'ytsearch10:{q}', download=False)
    except Exception as ex:
        logger.warning(f'Cautare esuata "{q}": {ex}')
        return jsonify(error=str(ex)), 500
    items = []
    for e in (info or {}).get('entries') or []:
        if not e or not e.get('id'):
            continue
        thumbs = e.get('thumbnails') or [{}]
        items.append({
            'id': e['id'],
            'title': e.get('title') or '',
            'artist': e.get('uploader') or e.get('channel') or '',
            'duration': e.get('duration') or 0,
            'thumb': thumbs[-1].get('url', ''),
        })
    logger.info(f'Cautare "{q}": {len(items)} rezultate')
    return jsonify(items)


@app.get('/api/resolve/<vid>')
def resolve(vid):
    if not VID_RE.match(vid):
        return jsonify(error='id invalid'), 400
    try:
        url, dur = audio_url(vid)
        return jsonify(url=url, duration=dur)
    except Exception as ex:
        logger.warning(f'Resolve esuat {vid}: {ex}')
        return jsonify(error=str(ex)), 500


@app.get('/api/audio/<vid>.mp3')
def audio_mp3(vid):
    # Releu + conversie in MP3: streamerele Linkplay/Arylic redau sigur MP3 pe HTTP,
    # dar nu si containerul m4a/webm venit de la YouTube. Convertim din mers cu ffmpeg.
    if not VID_RE.match(vid):
        return jsonify(error='id invalid'), 400
    ff = ffmpeg_path()
    if not ff:
        logger.warning('ffmpeg lipseste - trec pe audio brut')
        return audio(vid)
    try:
        url, _ = audio_url(vid)
    except Exception as ex:
        logger.warning(f'Audio(mp3) esuat {vid}: {ex}')
        return jsonify(error=str(ex)), 500
    args = [ff, '-hide_banner', '-loglevel', 'error', '-reconnect', '1',
            '-reconnect_streamed', '1', '-i', url,
            '-vn', '-f', 'mp3', '-ab', '192k', '-']
    proc = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))

    def gen():
        try:
            while True:
                chunk = proc.stdout.read(65536)
                if not chunk:
                    break
                yield chunk
        finally:
            try:
                proc.kill()
            except Exception:
                pass

    logger.info(f'Redau (mp3 via ffmpeg) {vid}')
    return app.response_class(gen(), mimetype='audio/mpeg')


@app.get('/api/audio/<vid>')
def audio(vid):
    # Releu audio brut (fallback fara ffmpeg): trece sunetul de la YouTube mai departe.
    if not VID_RE.match(vid):
        return jsonify(error='id invalid'), 400
    try:
        url, _ = audio_url(vid)
    except Exception as ex:
        logger.warning(f'Audio esuat {vid}: {ex}')
        return jsonify(error=str(ex)), 500
    up_headers = {}
    rng = request.headers.get('Range')
    if rng:
        up_headers['Range'] = rng
    try:
        upstream = requests.get(url, headers=up_headers, stream=True, timeout=20)
    except Exception as ex:
        logger.warning(f'Sursa audio inaccesibila {vid}: {ex}')
        return jsonify(error='nu pot accesa sursa audio: ' + str(ex)), 502

    def gen():
        try:
            for chunk in upstream.iter_content(64 * 1024):
                yield chunk
        finally:
            upstream.close()

    keep = ('content-type', 'content-length', 'content-range', 'accept-ranges')
    headers = {k: v for k, v in upstream.headers.items() if k.lower() in keep}
    return app.response_class(gen(), status=upstream.status_code, headers=headers)


@app.get('/api/cmd')
def devcmd():
    # Proxy de comenzi catre streamer: aplicatia poate CITI raspunsurile
    # (nume dispozitiv, volum, status redare), ceea ce browserul nu poate direct.
    ip = request.args.get('ip', '')
    c = request.args.get('c', '')
    if not IP_RE.match(ip):
        return jsonify(error='ip invalid'), 400
    if not CMD_RE.match(c):
        return jsonify(error='comanda respinsa'), 400
    try:
        r = requests.get(f'http://{ip}/httpapi.asp?command={c}', timeout=5)
        return app.response_class(r.text, mimetype='text/plain')
    except Exception as ex:
        logger.warning(f'Comanda catre {ip} esuata: {ex}')
        return jsonify(error=str(ex)), 502


@app.get('/api/discover')
def discover():
    # Scaneaza reteaua locala si gaseste streamerele Linkplay/Arylic
    import concurrent.futures
    base = lan_ip().rsplit('.', 1)[0]

    def probe(n):
        ipa = f'{base}.{n}'
        try:
            r = requests.get(f'http://{ipa}/httpapi.asp?command=getStatusEx', timeout=1.2)
            if r.ok:
                j = json.loads(r.text)
                name = j.get('DeviceName') or j.get('GroupName') or 'dispozitiv'
                return {'ip': ipa, 'name': name, 'firmware': j.get('firmware', '')}
        except Exception:
            pass
        return None

    found = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=64) as ex:
        for res in ex.map(probe, range(1, 255)):
            if res:
                found.append(res)
    logger.info(f'Scanare retea: {len(found)} streamere gasite')
    return jsonify(found)


@app.get('/api/playlist/<pid>')
def playlist(pid):
    if not PID_RE.match(pid):
        return jsonify(error='id invalid'), 400
    try:
        with yt_dlp.YoutubeDL({**BASE, 'extract_flat': True}) as ydl:
            info = ydl.extract_info(f'https://www.youtube.com/playlist?list={pid}', download=False)
        tracks = []
        for e in (info or {}).get('entries') or []:
            if not e or not e.get('id'):
                continue
            tracks.append({
                'id': e['id'],
                'title': e.get('title') or '',
                'artist': e.get('uploader') or '',
                'duration': e.get('duration') or 0,
                'thumb': '',
            })
        return jsonify(name=info.get('title') or 'Playlist YouTube', tracks=tracks)
    except Exception as ex:
        logger.warning(f'Import playlist esuat {pid}: {ex}')
        return jsonify(error=str(ex)), 500


# ---------- Auto-DJ: redare autonoma pe server, cu programare ----------
def _now_hm():
    lt = time.localtime()
    return lt.tm_hour * 60 + lt.tm_min


def active_preset():
    now = _now_hm()
    chosen = SCHEDULE[-1]['preset']  # inainte de prima ora = ultimul de aseara
    for s in SCHEDULE:
        h, m = s['from'].split(':')
        if now >= int(h) * 60 + int(m):
            chosen = s['preset']
    return chosen


def preset_track_ids(key):
    q = PRESETS.get(key, {}).get('query', '')
    if not q:
        return []
    try:
        with yt_dlp.YoutubeDL({**BASE, 'extract_flat': True}) as ydl:
            info = ydl.extract_info(f'ytsearch12:{q}', download=False)
        ids = []
        for e in (info or {}).get('entries') or []:
            if not e or not e.get('id'):
                continue
            d = e.get('duration') or 0
            if d and d < 180:   # sarim clipurile scurte, vrem mixuri lungi
                continue
            ids.append(e['id'])
        return ids[:8]
    except Exception as ex:
        logger.warning(f'Auto-DJ: cautare preset esuata {key}: {ex}')
        return []


def find_streamer_ip():
    if AUTODJ['ip'] and IP_RE.match(AUTODJ['ip']):
        return AUTODJ['ip']
    import concurrent.futures
    base = lan_ip().rsplit('.', 1)[0]

    def probe(n):
        ipa = f'{base}.{n}'
        try:
            r = requests.get(f'http://{ipa}/httpapi.asp?command=getStatusEx', timeout=1.0)
            if r.ok and 'DeviceName' in r.text:
                return ipa
        except Exception:
            pass
        return None
    with concurrent.futures.ThreadPoolExecutor(max_workers=64) as ex:
        for res in ex.map(probe, range(1, 255)):
            if res:
                AUTODJ['ip'] = res
                save_state()
                return res
    return ''


def autodj_play(vid, ip):
    try:
        _, dur = audio_url(vid)
    except Exception as ex:
        logger.warning(f'Auto-DJ: resolve esuat {vid}: {ex}')
        return 0
    url = f'{LAN_URL}/api/audio/{vid}.mp3'
    from urllib.parse import quote
    try:
        requests.get(f'http://{ip}/httpapi.asp?command=setPlayerCmd:play:{quote(url, safe="")}',
                     timeout=5)
    except Exception as ex:
        logger.warning(f'Auto-DJ: comanda play esuata: {ex}')
        return 0
    logger.info(f'Auto-DJ: redau {vid} ({dur}s) pe {ip}')
    return dur or 600


def autodj_loop():
    time.sleep(8)
    cur_key = None
    tracks = []
    idx = 0
    track_end = 0
    while True:
        try:
            if not AUTODJ['enabled'] or time.time() < AUTODJ['override_until']:
                cur_key = None  # la reactivare, reincepe preset-ul curent
                time.sleep(15)
                continue
            ip = find_streamer_ip()
            if not ip:
                logger.warning('Auto-DJ: niciun streamer gasit, reincerc.')
                time.sleep(30)
                continue
            want = active_preset()
            need_new = (want != cur_key) or (not tracks)
            if need_new:
                new_tracks = preset_track_ids(want)
                if not new_tracks:
                    time.sleep(30)
                    continue
                cur_key, tracks, idx = want, new_tracks, 0
                dur = autodj_play(tracks[idx], ip)
                track_end = time.time() + dur + 2
            elif time.time() >= track_end:
                idx = (idx + 1) % len(tracks)
                dur = autodj_play(tracks[idx], ip)
                track_end = time.time() + dur + 2
        except Exception:
            logger.exception('Auto-DJ: eroare in bucla')
        time.sleep(15)


@app.get('/api/presets')
def presets_list():
    return jsonify(active=active_preset(),
                   presets=[{'key': k, 'name': v['name']} for k, v in PRESETS.items()],
                   schedule=SCHEDULE)


@app.get('/api/preset/<key>')
def preset_tracks(key):
    # pentru redare manuala din UI: intoarce piesele preset-ului
    if key not in PRESETS:
        return jsonify(error='preset necunoscut'), 404
    ids = preset_track_ids(key)
    if not ids:
        return jsonify(error='nu am gasit piese acum'), 502
    out = []
    for vid in ids:
        try:
            _, dur = audio_url(vid)
        except Exception:
            dur = 0
        out.append({'id': vid, 'title': PRESETS[key]['name'], 'artist': '', 'duration': dur, 'thumb': ''})
    return jsonify(name=PRESETS[key]['name'], tracks=out)


@app.get('/api/autodj')
def autodj_get():
    return jsonify(enabled=AUTODJ['enabled'], ip=AUTODJ['ip'],
                   active=active_preset(),
                   override=max(0, int(AUTODJ['override_until'] - time.time())))


@app.get('/api/autodj/set')
def autodj_set():
    on = request.args.get('on')
    ip = request.args.get('ip', '')
    if IP_RE.match(ip):
        AUTODJ['ip'] = ip
    if on is not None:
        AUTODJ['enabled'] = on in ('1', 'true', 'on')
        AUTODJ['override_until'] = 0
    save_state()
    logger.info(f'Auto-DJ set: enabled={AUTODJ["enabled"]} ip={AUTODJ["ip"]}')
    return jsonify(ok=True, enabled=AUTODJ['enabled'], ip=AUTODJ['ip'])


@app.get('/api/autodj/pause')
def autodj_pause():
    # cand cineva redă manual din UI, punem Auto-DJ pe pauza temporar
    mins = int(request.args.get('min', '120') or 120)
    if AUTODJ['enabled']:
        AUTODJ['override_until'] = time.time() + mins * 60
    return jsonify(ok=True, override_min=mins)


if __name__ == '__main__':
    LAN_URL = f'http://{lan_ip()}:8321'
    load_state()
    logger.info(f'Zion Stream v{VERSION} pornit ({"exe" if FROZEN else "python"}) - {LAN_URL}')
    threading.Thread(target=_self_update_ytdlp, daemon=True).start()
    threading.Thread(target=update_loop, daemon=True).start()
    threading.Thread(target=logs_loop, daemon=True).start()
    threading.Thread(target=autodj_loop, daemon=True).start()
    print('=' * 50)
    print(f'  Zion Stream v{VERSION} pornit!')
    print('  Deschide in browser (PC sau telefon, acelasi net):')
    print(f'  {LAN_URL}')
    print('=' * 50)
    app.run(host='0.0.0.0', port=8321, threaded=True)
