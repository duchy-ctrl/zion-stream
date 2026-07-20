# Zion Stream - server local: extractie audio YouTube (yt-dlp) + releu audio HTTP
# pentru streamere Linkplay/Arylic + proxy de comenzi + auto-update din GitHub
# + logging cu upload optional in repo (token local in zion-config.json).
# Porneste cu: porneste-server.bat (sau automat, dupa instaleaza-autostart.bat)
import base64
import json
import logging
import os
import re
import socket
import subprocess
import sys
import threading
import time
from logging.handlers import RotatingFileHandler

from flask import Flask, request, jsonify
import requests
import yt_dlp

VERSION = '1.1.0'
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


@app.get('/api/audio/<vid>')
def audio(vid):
    # Releu audio: streamerul (care nu stie HTTPS) primeste HTTP simplu din LAN,
    # iar serverul trage sunetul de la YouTube si il trece mai departe.
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


if __name__ == '__main__':
    LAN_URL = f'http://{lan_ip()}:8321'
    logger.info(f'Zion Stream v{VERSION} pornit ({"exe" if FROZEN else "python"}) - {LAN_URL}')
    threading.Thread(target=_self_update_ytdlp, daemon=True).start()
    threading.Thread(target=update_loop, daemon=True).start()
    threading.Thread(target=logs_loop, daemon=True).start()
    print('=' * 50)
    print(f'  Zion Stream v{VERSION} pornit!')
    print('  Deschide in browser (PC sau telefon, acelasi net):')
    print(f'  {LAN_URL}')
    print('=' * 50)
    app.run(host='0.0.0.0', port=8321, threaded=True)
