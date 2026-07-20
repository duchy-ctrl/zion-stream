# Zion Stream - server local: extractie audio YouTube (yt-dlp) + releu audio HTTP
# pentru streamere Linkplay/Arylic + proxy de comenzi catre streamer.
# Porneste cu: porneste-server.bat (sau automat, dupa instaleaza-autostart.bat)
import os
import re
import sys
import time
import socket
import threading
import subprocess
from flask import Flask, request, jsonify
import requests
import yt_dlp

app = Flask(__name__)
BASE = {'quiet': True, 'no_warnings': True, 'skip_download': True, 'socket_timeout': 15}
DIR = os.path.dirname(os.path.abspath(__file__))
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


def _self_update():
    # yt-dlp se strica periodic cand YouTube schimba API-ul; il actualizam
    # in fundal la fiecare pornire (efectiv de la urmatoarea repornire)
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


@app.get('/')
def index():
    try:
        with open(os.path.join(DIR, 'zion-stream.html'), encoding='utf-8') as f:
            return f.read()
    except FileNotFoundError:
        return 'Pune zion-stream.html in acelasi folder cu zion-server.py', 404


@app.get('/api/ping')
def ping():
    return jsonify(ok=True, server='zion-stream', lan=LAN_URL)


@app.get('/api/search')
def search():
    q = request.args.get('q', '')
    if not q:
        return jsonify([])
    try:
        with yt_dlp.YoutubeDL({**BASE, 'extract_flat': True}) as ydl:
            info = ydl.extract_info(f'ytsearch10:{q}', download=False)
    except Exception as ex:
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
    return jsonify(items)


@app.get('/api/resolve/<vid>')
def resolve(vid):
    if not VID_RE.match(vid):
        return jsonify(error='id invalid'), 400
    try:
        url, dur = audio_url(vid)
        return jsonify(url=url, duration=dur)
    except Exception as ex:
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
        return jsonify(error=str(ex)), 500
    up_headers = {}
    rng = request.headers.get('Range')
    if rng:
        up_headers['Range'] = rng
    try:
        upstream = requests.get(url, headers=up_headers, stream=True, timeout=20)
    except Exception as ex:
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
        return jsonify(error=str(ex)), 502


@app.get('/api/discover')
def discover():
    # Scaneaza reteaua locala si gaseste streamerele Linkplay/Arylic
    import concurrent.futures
    import json as _json
    base = lan_ip().rsplit('.', 1)[0]

    def probe(n):
        ipa = f'{base}.{n}'
        try:
            r = requests.get(f'http://{ipa}/httpapi.asp?command=getStatusEx', timeout=1.2)
            if r.ok:
                j = _json.loads(r.text)
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
        return jsonify(error=str(ex)), 500


if __name__ == '__main__':
    LAN_URL = f'http://{lan_ip()}:8321'
    threading.Thread(target=_self_update, daemon=True).start()
    print('=' * 50)
    print('  Zion Stream server pornit!')
    print('  Deschide in browser (PC sau telefon, acelasi net):')
    print(f'  {LAN_URL}')
    print('=' * 50)
    app.run(host='0.0.0.0', port=8321, threaded=True)
