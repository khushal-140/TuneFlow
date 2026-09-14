"""Link import helpers.

Three link kinds:
  * YouTube  -> stores the official embed URL (nothing is downloaded)
  * SoundCloud -> official oEmbed player (nothing is downloaded)
  * Direct audio URL -> downloaded to the server after an explicit rights check

All network calls are best-effort: if the machine is offline we degrade to
URL-derived metadata instead of failing the import.
"""
import json
import os
import re
import tempfile
import urllib.parse
import urllib.request

USER_AGENT = 'TuneFlow/1.0 (+self-hosted personal music library)'
AUDIO_EXTS = {'.mp3', '.m4a', '.flac', '.wav', '.ogg', '.oga', '.opus', '.aac', '.wma'}
MAX_DOWNLOAD_BYTES = 200 * 1024 * 1024

YT_ID_RE = re.compile(
    r'(?:youtube\.com/(?:watch\?(?:.*&)?v=|embed/|shorts/|live/)|youtu\.be/)([A-Za-z0-9_-]{11})'
)
SC_IFRAME_RE = re.compile(r'src="(https://w\.soundcloud\.com/player[^"]+)"')


def _fetch_json(url, timeout=8):
    try:
        req = urllib.request.Request(url, headers={'User-Agent': USER_AGENT})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode('utf-8', 'replace'))
    except Exception:
        return None


def _download(url, timeout=25):
    req = urllib.request.Request(url, headers={'User-Agent': USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def _head_info(url):
    """Content-type + size of a direct URL; falls back to a 1-byte ranged GET."""
    req = urllib.request.Request(url, headers={'User-Agent': USER_AGENT}, method='HEAD')
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.headers.get('Content-Type'), resp.headers.get('Content-Length')
    except Exception:
        pass
    try:
        req = urllib.request.Request(url, headers={'User-Agent': USER_AGENT, 'Range': 'bytes=0-0'})
        with urllib.request.urlopen(req, timeout=10) as resp:
            length = resp.headers.get('Content-Range', '')
            total = length.split('/')[-1] if '/' in length else resp.headers.get('Content-Length')
            return resp.headers.get('Content-Type'), total
    except Exception:
        return None, None


def classify(url):
    """Returns (kind, info): kind in {'youtube','soundcloud','audio','invalid'}."""
    url = (url or '').strip()
    if not re.match(r'^https?://', url, re.I):
        return 'invalid', {'reason': 'Please paste a full http(s) link.'}
    host = urllib.parse.urlparse(url).netloc.lower()

    m = YT_ID_RE.search(url)
    if m or 'youtube.com' in host or 'youtu.be' in host:
        vid = m.group(1) if m else None
        if not vid:
            return 'invalid', {'reason': 'Could not find a YouTube video ID in that link.'}
        meta = _fetch_json('https://www.youtube.com/oembed?format=json&url=' + urllib.parse.quote(url, safe='')) or {}
        return 'youtube', {
            'video_id': vid,
            'title': meta.get('title'),
            'artist': meta.get('author_name'),
            'thumbnail': meta.get('thumbnail_url') or f'https://i.ytimg.com/vi/{vid}/hqdefault.jpg',
            'embed_url': f'https://www.youtube-nocookie.com/embed/{vid}?autoplay=1&rel=0',
        }

    if 'soundcloud.com' in host:
        path = urllib.parse.urlparse(url).path.strip('/').split('/')
        if not path or not path[0]:
            return 'invalid', {'reason': 'That does not look like a SoundCloud track or playlist URL.'}
        meta = _fetch_json('https://soundcloud.com/oembed?format=json&url=' + urllib.parse.quote(url, safe='')) or {}
        embed = None
        if meta.get('html'):
            m2 = SC_IFRAME_RE.search(meta['html'])
            if m2:
                embed = m2.group(1)
        if not embed:
            embed = ('https://w.soundcloud.com/player/?url=' + urllib.parse.quote(url, safe='')
                     + '&color=%238b5cf6&auto_play=true&hide_cover=false&visual=false')
        return 'soundcloud', {
            'title': meta.get('title'),
            'artist': meta.get('author_name'),
            'thumbnail': meta.get('thumbnail_url'),
            'embed_url': embed,
        }

    # Anything else: treat as a candidate direct audio file.
    ctype, length = _head_info(url)
    path = urllib.parse.urlparse(url).path
    ext = os.path.splitext(path)[1].lower()
    is_audio = (ctype or '').lower().startswith('audio/') or ext in AUDIO_EXTS
    if not is_audio:
        return 'invalid', {'reason': 'That link is not a YouTube/SoundCloud page or a direct audio file.'}
    try:
        size = int(length) if length else None
    except (TypeError, ValueError):
        size = None
    return 'audio', {
        'content_type': ctype,
        'size': size,
        'filename': os.path.basename(path) or 'download',
    }


def download_audio(url, upload_dir, original_name=''):
    """Streams a direct audio URL to disk; returns (path_on_disk, stored_name)."""
    ext = os.path.splitext(urllib.parse.urlparse(url).path)[1].lower()
    if ext not in AUDIO_EXTS:
        ext = '.mp3'
    stored = uuid_name(ext)
    fd, tmp = tempfile.mkstemp(suffix=ext)
    os.close(fd)
    req = urllib.request.Request(url, headers={'User-Agent': USER_AGENT})
    total = 0
    try:
        with urllib.request.urlopen(req, timeout=30) as resp, open(tmp, 'wb') as fh:
            while True:
                chunk = resp.read(256 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > MAX_DOWNLOAD_BYTES:
                    raise ValueError('That file is larger than the 200 MB limit.')
                fh.write(chunk)
        os.replace(tmp, os.path.join(upload_dir, stored))
        return os.path.join(upload_dir, stored), stored
    finally:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass


def fetch_image(url):
    """Best-effort artwork download for embed tracks (their public thumbnail)."""
    if not url or not re.match(r'^https?://', url):
        return None
    try:
        data = _download(url, timeout=10)
        if len(data) > 10 * 1024 * 1024:
            return None
        return data
    except Exception:
        return None


def uuid_name(ext):
    import uuid
    return uuid.uuid4().hex + ext
