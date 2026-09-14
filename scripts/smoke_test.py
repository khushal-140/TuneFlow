"""End-to-end API smoke test for TuneFlow.

Start the server first (python run.py), then:
    python scripts/smoke_test.py
"""
import http.cookiejar
import json
import math
import os
import shutil
import sys
import tempfile
import threading
import urllib.error
import urllib.request
import uuid
from functools import partial
from http.server import HTTPServer, SimpleHTTPRequestHandler

BASE = os.environ.get('TUNEFLOW_BASE', 'http://127.0.0.1:5000')

PASS, FAIL = 0, 0


def check(name, cond, detail=''):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f'  PASS  {name}')
    else:
        FAIL += 1
        print(f'  FAIL  {name}  {detail}')


class Client:
    def __init__(self, base):
        self.base = base
        self.cj = http.cookiejar.CookieJar()
        self.op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.cj))

    def req(self, method, path, data=None, raw=None, ctype=None):
        url = self.base + path
        headers = {}
        body = None
        if raw is not None:
            body = raw
            headers['Content-Type'] = ctype
        elif data is not None:
            body = json.dumps(data).encode()
            headers['Content-Type'] = 'application/json'
        r = urllib.request.Request(url, data=body, method=method, headers=headers)
        try:
            with self.op.open(r, timeout=60) as resp:
                payload = resp.read().decode('utf-8', 'replace')
                try:
                    return resp.status, json.loads(payload)
                except ValueError:
                    return resp.status, {'raw': payload[:80]}
        except urllib.error.HTTPError as e:
            payload = e.read().decode('utf-8', 'replace')
            try:
                return e.code, json.loads(payload)
            except Exception:
                return e.code, {}
        except Exception as e:
            return 0, {'error': str(e)}


def multipart(fields, files):
    b = '----tfs' + uuid.uuid4().hex
    out = bytearray()
    for k, v in fields.items():
        out += f'--{b}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode()
    for k, (fname, blob, ctype) in files.items():
        out += f'--{b}\r\nContent-Disposition: form-data; name="{k}"; filename="{fname}"\r\nContent-Type: {ctype}\r\n\r\n'.encode()
        out += blob + b'\r\n'
    out += f'--{b}--\r\n'.encode()
    return bytes(out), f'multipart/form-data; boundary={b}'


def make_wav(path, seconds=4, rate=16000):
    import struct
    import wave as wavemod
    frames = bytearray()
    for i in range(seconds * rate):
        t = i / rate
        v = 0.35 * math.sin(2 * math.pi * 440 * t) * math.exp(-t * 0.5)
        frames += struct.pack('<h', int(v * 32767))
    w = wavemod.open(path, 'wb')
    w.setnchannels(1)
    w.setsampwidth(2)
    w.setframerate(rate)
    w.writeframes(bytes(frames))
    w.close()


def tag_wav(path, title, artist, album, genre, png_bytes):
    """Tag a WAV via mutagen (writes an ID3 chunk prepended before RIFF —
    exactly the quirky layout our server-side fallback must survive)."""
    from mutagen.id3 import APIC, ID3, TALB, TCON, TIT2, TPE1
    from mutagen.wave import WAVE
    w = WAVE(path)
    w.tags = ID3()
    w.tags.add(TIT2(encoding=3, text=title))
    w.tags.add(TPE1(encoding=3, text=artist))
    w.tags.add(TALB(encoding=3, text=album))
    w.tags.add(TCON(encoding=3, text=genre))
    w.tags.add(APIC(encoding=3, mime='image/png', type=3, desc='Cover', data=png_bytes))
    w.save()


TINY_PNG = bytes.fromhex(
    '89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489'
    '0000000d4944415478da63fcffff3f030005fe02fea72d1e480000000049454e44ae426082')


def main():
    print(f'TuneFlow smoke test against {BASE}')
    c = Client(BASE)

    print('\n[health]')
    s, d = c.req('GET', '/api/health')
    check('health endpoint', s == 200 and d.get('ok') is True, d)

    print('\n[auth]')
    uname = 'smoke_' + uuid.uuid4().hex[:8]
    s, d = c.req('POST', '/api/auth/register', {'username': uname, 'email': uname + '@test.io', 'password': 'secret1'})
    check('register', s == 200 and d.get('user', {}).get('username') == uname, d)
    s, d = c.req('POST', '/api/auth/logout')
    check('logout', s == 200)
    s, d = c.req('POST', '/api/auth/login', {'identifier': uname, 'password': 'wrong'})
    check('wrong password rejected', s == 401)
    s, d = c.req('POST', '/api/auth/login', {'identifier': uname, 'password': 'secret1'})
    check('login', s == 200 and d.get('user', {}).get('username') == uname, d)
    s, d = c.req('GET', '/api/me')
    check('me', s == 200 and d.get('user', {}).get('username') == uname)

    print('\n[songs + likes + history]')
    s, d = c.req('GET', '/api/songs')
    check('songs list (empty ok)', s == 200 and 'songs' in d, d)

    print('\n[upload: untagged wav -> filename parsing]')
    tmpdir = tempfile.mkdtemp()
    try:
        plain_path = os.path.join(tmpdir, 'plain.wav')
        make_wav(plain_path)
        with open(plain_path, 'rb') as fh:
            plain_bytes = fh.read()
        body, ctype = multipart({}, {'file': ('Smoke Artist - Filename Song.wav', plain_bytes, 'audio/wav')})
        s, d = c.req('POST', '/api/upload', raw=body, ctype=ctype)
        songs = d.get('songs', [])
        check('untagged upload creates song', s == 200 and len(songs) == 1, d)
        song = songs[0] if songs else {}
        check('title parsed from filename', song.get('title') == 'Filename Song', song.get('title'))
        check('artist parsed from filename', song.get('artist') == 'Smoke Artist', song.get('artist'))

        print('\n[upload: mutagen-tagged wav -> tags + cover art]')
        wav_path = os.path.join(tmpdir, 'tagged.wav')
        make_wav(wav_path)
        tag_wav(wav_path, 'Smoke Test Song', 'Smoke Artist', 'Smoke Album', 'SmokeCore', TINY_PNG)
        with open(wav_path, 'rb') as fh:
            wav_bytes = fh.read()
        body, ctype = multipart({}, {'file': ('tagged.wav', wav_bytes, 'audio/wav')})
        s, d = c.req('POST', '/api/upload', raw=body, ctype=ctype)
        songs = d.get('songs', [])
        check('tagged upload creates song', s == 200 and len(songs) == 1, d)
        tagged = songs[0] if songs else {}
        check('title extracted from tag', tagged.get('title') == 'Smoke Test Song', tagged.get('title'))
        check('artist extracted', tagged.get('artist') == 'Smoke Artist', tagged.get('artist'))
        check('album extracted', tagged.get('album') == 'Smoke Album', tagged.get('album'))
        check('genre extracted', tagged.get('genre') == 'SmokeCore', tagged.get('genre'))
        check('duration extracted', abs((tagged.get('duration') or 0) - 4.0) < 0.5, tagged.get('duration'))
        check('cover art extracted', bool(tagged.get('cover')), tagged.get('cover'))
        if tagged.get('cover'):
            s2, _ = c.req('GET', tagged['cover'])
            check('cover served', s2 == 200)
        if tagged.get('stream'):
            s3, _ = c.req('GET', tagged['stream'])
            check('audio stream served', s3 == 200)

        print('\n[song update / like / play]')
        s, d = c.req('PATCH', f"/api/songs/{song['id']}", {'title': 'Renamed', 'genre': 'Test'})
        check('patch metadata', s == 200 and d.get('song', {}).get('title') == 'Renamed', d)
        s, d = c.req('POST', f"/api/songs/{song['id']}/like")
        check('like', s == 200 and d.get('liked') is True)
        s, d = c.req('POST', f"/api/songs/{song['id']}/like")
        check('unlike (toggle)', s == 200 and d.get('liked') is False)
        s, d = c.req('POST', f"/api/songs/{song['id']}/like")
        check('like again', s == 200 and d.get('liked') is True)
        s, d = c.req('POST', f"/api/songs/{song['id']}/play")
        check('record play', s == 200 and d.get('play_count') == 1, d)
        s, d = c.req('GET', '/api/likes')
        check('likes list', s == 200 and len(d.get('songs', [])) == 1)
        s, d = c.req('GET', '/api/history')
        check('history recorded', s == 200 and len(d.get('history', [])) == 1)
        s, d = c.req('GET', '/api/songs/facets')
        check('facets', s == 200 and 'Test' in d.get('genres', []), d)

        print('\n[playlists]')
        s, d = c.req('POST', '/api/playlists', {'name': 'Smoke Mix', 'description': 'test'})
        pl = d.get('playlist', {})
        check('create playlist', s == 200 and pl.get('name') == 'Smoke Mix', d)
        s, d = c.req('POST', f"/api/playlists/{pl['id']}/songs", {'song_id': song['id']})
        check('add song', s == 200 and d.get('added') == [song['id']], d)
        s, d = c.req('POST', f"/api/playlists/{pl['id']}/songs", {'song_id': song['id']})
        check('duplicate skipped', s == 200 and d.get('added') == [], d)
        s, d = c.req('GET', f"/api/playlists/{pl['id']}")
        check('playlist detail', s == 200 and len(d.get('playlist', {}).get('songs', [])) == 1)
        s, d = c.req('DELETE', f"/api/playlists/{pl['id']}/songs/{song['id']}")
        check('remove song', s == 200)
        s, d = c.req('DELETE', f"/api/playlists/{pl['id']}")
        check('delete playlist', s == 200)

        print('\n[recommendations + assistant]')
        s, d = c.req('GET', '/api/recommendations')
        check('recommendations endpoint', s == 200 and 'songs' in d, d)
        s, d = c.req('POST', '/api/assistant', {'message': 'play something by Smoke Artist'})
        check('assistant artist search', s == 200 and len(d.get('tracks', [])) >= 1, d)
        s, d = c.req('POST', '/api/assistant', {'message': 'make me a 30-minute study playlist'})
        check('assistant duration+mood', s == 200 and 'tracks' in d, d)

        print('\n[link import]')
        s, d = c.req('POST', '/api/import/preview', {'url': 'https://www.youtube.com/watch?v=dQw4w9WgXcQ'})
        check('youtube preview', s == 200 and d.get('kind') == 'youtube', d)
        s, d = c.req('POST', '/api/import/confirm', {'url': 'https://www.youtube.com/watch?v=dQw4w9WgXcQ'})
        yt_song = d.get('song', {})
        check('youtube confirm -> embed song', s == 200 and yt_song.get('embed_url'), d)
        check('youtube: nothing downloaded', yt_song.get('source') == 'youtube' and not yt_song.get('stream'))

        s, d = c.req('POST', '/api/import/preview', {'url': 'not a url'})
        check('invalid url rejected', s == 400)

        # local HTTP server serving a wav for the direct-download flow
        os.makedirs(os.path.join(tmpdir, 'srv'), exist_ok=True)
        dl_path = os.path.join(tmpdir, 'srv', 'testsong.wav')
        make_wav(dl_path, seconds=2)
        handler = partial(SimpleHTTPRequestHandler, directory=os.path.join(tmpdir, 'srv'))
        srv = HTTPServer(('127.0.0.1', 0), handler)
        port = srv.server_address[1]
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            direct = f'http://127.0.0.1:{port}/testsong.wav'
            s, d = c.req('POST', '/api/import/preview', {'url': direct})
            check('direct audio preview', s == 200 and d.get('kind') == 'audio' and d.get('info', {}).get('requires_rights'), d)
            s, d = c.req('POST', '/api/import/confirm', {'url': direct, 'rights_confirmed': False})
            check('download blocked without rights', s == 403, d)
            s, d = c.req('POST', '/api/import/confirm', {'url': direct, 'rights_confirmed': True})
            dl_song = d.get('song', {})
            check('download with rights', s == 200 and dl_song.get('stream') is not None, d)
            check('downloaded file got tags/duration', abs((dl_song.get('duration') or 0) - 2.0) < 0.5, dl_song.get('duration'))

            print('\n[cleanup + delete]')
            if yt_song.get('id'):
                s, _ = c.req('DELETE', f"/api/songs/{yt_song['id']}")
                check('delete embed song', s == 200)
            if dl_song.get('id'):
                s, _ = c.req('DELETE', f"/api/songs/{dl_song['id']}")
                check('delete downloaded song', s == 200)
            if song.get('id'):
                s, _ = c.req('DELETE', f"/api/songs/{song['id']}")
                check('delete untagged song', s == 200)
            if tagged.get('id'):
                s, _ = c.req('DELETE', f"/api/songs/{tagged['id']}")
                check('delete tagged song', s == 200)
                s, d = c.req('GET', '/api/songs')
                check('library empty again', s == 200 and d.get('total') == 0, d)
        finally:
            srv.shutdown()
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)

    print('\n[demo account]')
    s, d = c.req('POST', '/api/auth/logout')
    s, d = c.req('POST', '/api/auth/login', {'identifier': 'demo', 'password': 'demo123'})
    if s == 200:
        s, d = c.req('GET', '/api/songs')
        check('demo library seeded', d.get('total', 0) >= 10, d.get('total'))
        s, d = c.req('GET', '/api/home')
        check('home feed', s == 200 and d.get('stats', {}).get('songs', 0) >= 10)
        check('recommendations personalized', d.get('rec_mode') == 'personalized', d.get('rec_mode'))
        s, d = c.req('POST', '/api/assistant', {'message': 'make me a 30-minute study playlist'})
        check('demo assistant works', s == 200 and len(d.get('tracks', [])) >= 3, len(d.get('tracks', [])))
    else:
        print('  SKIP  demo account not seeded (run seed_data.py)')

    print(f'\nResult: {PASS} passed, {FAIL} failed')
    sys.exit(1 if FAIL else 0)


if __name__ == '__main__':
    main()
