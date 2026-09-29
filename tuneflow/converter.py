"""YouTube → MP3 converter section.

Adapted from the user's standalone "YouTube To MP3 (Music) Project" (yt-dlp +
FFmpegExtractAudio 192 kbps + FFmpegMetadata + EmbedThumbnail), integrated with
TuneFlow's library: downloads run as background jobs with progress polling, the
finished MP3 is re-read with Mutagen, stored in static/uploads like any upload,
and added to the requesting user's library with source='ytdownload'.

Rights gate: /api/convert/start refuses to run unless the client explicitly
sends rights_confirmed=true (the UI shows the confirmation checkbox).

Cloud hosts: YouTube blocks datacenter IPs ("Sign in to confirm you're not a
bot"). Set the YT_COOKIES env var (Netscape cookies.txt content exported from
your browser) or YT_COOKIES_FILE (path) and it is passed to yt-dlp.
"""
import os
import shutil
import tempfile
import threading
import uuid

from flask import Blueprint, current_app, jsonify, request

from .extensions import db
from .helpers import bad_request, login_required
from .metadata import extract_metadata, save_cover
from .models import Song

converter_bp = Blueprint('converter', __name__)

JOBS = {}
JOBS_LOCK = threading.Lock()

FFMPEG_MISSING = ('ffmpeg was not found on this server. The build command downloads a static '
                  'binary into bin/ automatically ("curl -fsSL .../ffmpeg-linux-x64 -o bin/ffmpeg") '
                  '— or install ffmpeg system-wide and restart TuneFlow.')


def _ffmpeg_binary():
    """Locate ffmpeg for yt-dlp: FFMPEG_PATH env, repo bin/ (Render build), or PATH."""
    p = os.environ.get('FFMPEG_PATH', '').strip()
    if p and (os.path.isfile(p) or os.path.isdir(p)):
        return p
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    bdir = os.path.join(root, 'bin')
    if os.path.isdir(bdir) and os.access(bdir, os.X_OK):
        if any(os.path.isfile(os.path.join(bdir, n)) for n in ('ffmpeg', 'ffmpeg.exe')):
            return bdir  # yt-dlp finds ffmpeg/ffprobe inside this directory
    which = shutil.which('ffmpeg')
    return which or None


def _friendly_error(e):
    """Translate raw yt-dlp errors into something actionable."""
    msg = str(e)
    low = msg.lower()
    if 'sign in to confirm' in low or 'not a bot' in low:
        return ('YouTube is blocking this server ("Sign in to confirm you are not a bot"). '
                'Cloud hosts like Render run on datacenter IPs that YouTube does not trust — '
                'this is not a TuneFlow bug. Fix: click "Configure cookies" above and paste your '
                'cookies.txt content (export it on youtube.com with the browser extension '
                '"Get cookies.txt LOCALLY"). Alternatively set the YT_COOKIES environment variable '
                'on Render. On your home PC the converter works without any setup.')
    if 'ffmpeg' in low:
        return FFMPEG_MISSING
    return msg


_COOKIES_CACHE = None


def _instance_cookie_file():
    """Path of cookies saved from the UI (instance/cookies.txt)."""
    try:
        return os.path.join(current_app.instance_path, 'cookies.txt')
    except RuntimeError:
        return None


def _cookie_file():
    """Resolve a cookies.txt for yt-dlp: env var, env file path, or UI-saved file."""
    global _COOKIES_CACHE
    if _COOKIES_CACHE is not None:
        return _COOKIES_CACHE or None
    path = os.environ.get('YT_COOKIES_FILE', '').strip()
    if not path:
        raw = os.environ.get('YT_COOKIES', '').strip()
        if raw:
            fd, path = tempfile.mkstemp(prefix='tf-yt-cookies-', suffix='.txt')
            with os.fdopen(fd, 'w', encoding='utf-8') as fh:
                fh.write(raw.replace('\\r\\n', '\n').replace('\\n', '\n'))
    if not path:
        inst = _instance_cookie_file()
        if inst and os.path.exists(inst):
            path = inst
    _COOKIES_CACHE = path if path and os.path.exists(path) else ''
    return _COOKIES_CACHE or None


def _set_job(job_id, **fields):
    with JOBS_LOCK:
        job = JOBS.setdefault(job_id, {'percentage': 0, 'stage': 'Starting…', 'done': False})
        job.update(fields)
        return dict(job)


def _get_job(job_id):
    with JOBS_LOCK:
        return dict(JOBS.get(job_id) or {})


def _hook(job_id):
    def progress_hook(data):
        if data.get('status') == 'downloading':
            total = data.get('total_bytes') or data.get('total_bytes_estimate')
            done = data.get('downloaded_bytes', 0)
            if total:
                _set_job(job_id, percentage=round(done / total * 95, 1), stage='Downloading audio…')
        elif data.get('status') == 'finished':
            _set_job(job_id, percentage=96, stage='Converting to MP3 (ffmpeg)…')
    return progress_hook


def _check_ffmpeg():
    return _ffmpeg_binary() is not None


def _ydl_options(upload_dir, stem, job_id):
    options = {
        'format': 'bestaudio/best',
        'outtmpl': os.path.join(upload_dir, stem + '.%(ext)s'),
        'noplaylist': True,
        'quiet': True,
        'no_warnings': True,
        'max_filesize': 200 * 1024 * 1024,
        'writethumbnail': True,  # downloaded then embedded into the MP3 by the postprocessor
        'progress_hooks': [_hook(job_id)],
        'postprocessors': [
            {'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3', 'preferredquality': '192'},
            {'key': 'FFmpegMetadata'},
            {'key': 'EmbedThumbnail'},
        ],
    }
    cookies = _cookie_file()
    if cookies:
        options['cookiefile'] = cookies
    ffmpeg = _ffmpeg_binary()
    if ffmpeg:
        options['ffmpeg_location'] = ffmpeg
    return options


@converter_bp.get('/api/convert/cookies')
@login_required
def cookies_status(user):
    global _COOKIES_CACHE
    src = None
    if os.environ.get('YT_COOKIES_FILE', '').strip():
        src = 'env-file'
    elif os.environ.get('YT_COOKIES', '').strip():
        src = 'env'
    else:
        inst = _instance_cookie_file()
        if inst and os.path.exists(inst):
            src = 'ui'
    _COOKIES_CACHE = None  # re-resolve on next use
    return jsonify(set=src is not None, source=src)


@converter_bp.post('/api/convert/cookies')
@login_required
def save_cookies(user):
    """Save cookies.txt pasted from the UI (stored privately on this server)."""
    global _COOKIES_CACHE
    data = request.get_json(silent=True) or {}
    content = (data.get('content') or '').strip()
    if not content:
        return bad_request('Paste your cookies.txt content first.')
    if '# Netscape' not in content and '\t' not in content:
        return bad_request("That doesn't look like a cookies.txt file. On youtube.com use the "
                           "'Get cookies.txt LOCALLY' browser extension to export it, then paste "
                           "the whole file here.")
    inst_dir = current_app.instance_path
    os.makedirs(inst_dir, exist_ok=True)
    with open(os.path.join(inst_dir, 'cookies.txt'), 'w', encoding='utf-8') as fh:
        fh.write(content if content.endswith('\n') else content + '\n')
    _COOKIES_CACHE = None  # re-resolve on next use
    return jsonify(ok=True, set=True, source='ui',
                   message='Cookies saved — the converter will use them from now on.')


@converter_bp.delete('/api/convert/cookies')
@login_required
def clear_cookies(user):
    global _COOKIES_CACHE
    inst = _instance_cookie_file()
    if inst and os.path.exists(inst):
        os.remove(inst)
    _COOKIES_CACHE = None
    return jsonify(ok=True, set=False, source=None)


@converter_bp.post('/api/convert/preview')
@login_required
def preview(user):
    import yt_dlp

    data = request.get_json(silent=True) or {}
    url = (data.get('url') or '').strip()
    if not url:
        return bad_request('Paste a YouTube link first.')
    if not _check_ffmpeg():
        return bad_request(FFMPEG_MISSING)

    opts = {'quiet': True, 'no_warnings': True, 'noplaylist': True, 'skip_download': True}
    cookies = _cookie_file()
    if cookies:
        opts['cookiefile'] = cookies
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
    except Exception as e:
        return bad_request(f'Could not read that video: {_friendly_error(e)}')

    if info.get('_type') in ('playlist', 'multi_video') and info.get('entries'):
        entries = list(info['entries'])
        if len(entries) != 1:
            return bad_request('That link points to a playlist — paste a single video URL.')
        info = entries[0]

    return jsonify(preview={
        'title': info.get('title') or 'Unknown Title',
        'artist': info.get('artist') or info.get('uploader') or info.get('channel') or 'YouTube',
        'duration': info.get('duration') or 0,
        'thumbnail': info.get('thumbnail'),
        'uploader': info.get('uploader') or info.get('channel') or '',
        'webpage_url': info.get('webpage_url') or url,
        'id': info.get('id'),
    })


@converter_bp.post('/api/convert/start')
@login_required
def start(user):
    data = request.get_json(silent=True) or {}
    url = (data.get('url') or '').strip()
    if not url:
        return bad_request('Paste a YouTube link first.')
    if not bool(data.get('rights_confirmed')):
        return jsonify(error='Please confirm you have the rights to download and keep this audio.'), 403
    if not _check_ffmpeg():
        return bad_request(FFMPEG_MISSING)

    overrides = {
        'title': (data.get('title') or '').strip()[:255] or None,
        'artist': (data.get('artist') or '').strip()[:255] or None,
        'album': (data.get('album') or '').strip()[:255] or None,
        'genre': (data.get('genre') or '').strip()[:64] or None,
    }

    job_id = uuid.uuid4().hex
    _set_job(job_id, percentage=0, stage='Getting video information…', song_id=None, error=None)

    app = current_app._get_current_object()
    worker = threading.Thread(
        target=_run_conversion, args=(app, user.id, job_id, url, overrides), daemon=True)
    worker.start()
    return jsonify(job_id=job_id)


@converter_bp.get('/api/convert/status/<job_id>')
@login_required
def status(user, job_id):
    job = _get_job(job_id)
    if not job:
        return jsonify(error='Unknown job.'), 404
    payload = {
        'percentage': job.get('percentage', 0),
        'stage': job.get('stage', ''),
        'done': bool(job.get('done')),
        'error': job.get('error'),
    }
    if job.get('song_id'):
        song = Song.query.filter_by(id=job['song_id'], user_id=user.id).first()
        payload['song'] = song.to_dict() if song else None
    return jsonify(**payload)


def _run_conversion(app, user_id, job_id, url, overrides):
    import yt_dlp

    with app.app_context():
        try:
            upload_dir = app.config['UPLOAD_DIR']
            cover_dir = app.config['COVER_DIR']
            stem = uuid.uuid4().hex

            _set_job(job_id, stage='Downloading audio…')
            with yt_dlp.YoutubeDL(_ydl_options(upload_dir, stem, job_id)) as ydl:
                info = ydl.extract_info(url, download=True)

            mp3_path = os.path.join(upload_dir, stem + '.mp3')
            if not os.path.exists(mp3_path):
                # Some sources finish without re-encoding (already-MP3 format).
                candidates = [f for f in os.listdir(upload_dir) if f.startswith(stem + '.')]
                if not candidates:
                    raise RuntimeError('The conversion produced no audio file.')
                os.rename(os.path.join(upload_dir, candidates[0]), mp3_path)
            # Remove stray thumbnail files left over from a failed embed.
            for f in os.listdir(upload_dir):
                if f.startswith(stem + '.') and f != stem + '.mp3':
                    try:
                        os.remove(os.path.join(upload_dir, f))
                    except OSError:
                        pass

            _set_job(job_id, percentage=98, stage='Reading tags & cover art…')

            title = artist = album = genre = None
            duration = 0.0
            cover = None
            try:
                meta = extract_metadata(mp3_path)
                title, artist, album, genre = meta['title'], meta['artist'], meta['album'], meta['genre']
                duration = meta['duration'] or 0.0
                cover = meta.get('cover')
            except Exception:
                pass

            if not duration and info.get('duration'):
                duration = float(info['duration'])

            if not title:
                title = overrides['title'] or info.get('title') or 'Unknown Title'
            if overrides['title']:
                title = overrides['title']
            if overrides['artist']:
                artist = overrides['artist']
            elif not artist or artist == 'Unknown Artist':
                artist = (info.get('artist') or info.get('uploader')
                          or info.get('channel') or 'YouTube')
            if overrides['album']:
                album = overrides['album']
            elif not album:
                album = ''
            if overrides['genre']:
                genre = overrides['genre']
            elif not genre or genre == 'Unknown Genre':
                genre = 'Music'

            song = Song(
                user_id=user_id,
                title=(title or 'Unknown Title')[:255],
                artist=(artist or 'YouTube')[:255],
                album=(album or '')[:255],
                genre=(genre or 'Music')[:64],
                duration=round(float(duration or 0.0), 2),
                source='ytdownload',
                file_path=f'uploads/{stem}.mp3',
                external_url=info.get('webpage_url') or url,
                original_name=(f"{info.get('id')}.mp3" if info.get('id') else None),
            )
            if cover:
                try:
                    song.cover_path = save_cover(cover[0], cover[1], cover_dir)
                except Exception:
                    song.cover_path = None

            db.session.add(song)
            db.session.commit()

            _set_job(job_id, percentage=100, stage='Complete', done=True, song_id=song.id)
        except Exception as e:
            _set_job(job_id, stage='Failed', done=True, error=_friendly_error(e))
