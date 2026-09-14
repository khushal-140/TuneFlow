"""Smart upload (Mutagen) and smart link import endpoints."""
import os

from flask import Blueprint, current_app, jsonify, request

from .extensions import db
from .helpers import bad_request, login_required
from .links import classify, download_audio, fetch_image
from .metadata import (ALLOWED_EXTS, extract_metadata, save_cover,
                       title_from_filename)
from .models import Song

uploads_bp = Blueprint('uploads', __name__)

SOURCE_LABEL = {
    'upload': 'Upload',
    'download': 'Link download',
    'youtube': 'YouTube embed',
    'soundcloud': 'SoundCloud embed',
}


def _finalize_metadata(meta, filename, overrides=None):
    """Fill gaps in extracted tags; filename parsing as fallback."""
    overrides = overrides or {}
    title = overrides.get('title') or meta.get('title')
    artist = overrides.get('artist') or meta.get('artist')
    if not title:
        parsed_title, parsed_artist = title_from_filename(filename)
        title = parsed_title or os.path.splitext(os.path.basename(filename))[0]
        artist = artist or parsed_artist or 'Unknown Artist'
    return {
        'title': title.strip()[:255] or 'Untitled',
        'artist': (artist or 'Unknown Artist').strip()[:255],
        'album': (overrides.get('album') or meta.get('album') or '').strip()[:255],
        'genre': (overrides.get('genre') or meta.get('genre') or '').strip()[:64],
        'duration': float(meta.get('duration') or 0.0),
    }


@uploads_bp.post('/api/upload')
@login_required
def upload(user):
    files = request.files.getlist('file') or request.files.getlist('files')
    if not files:
        return bad_request('No file received — pick an audio file first.')

    upload_dir = current_app.config['UPLOAD_DIR']
    cover_dir = current_app.config['COVER_DIR']
    created, errors = [], []

    for fs in files:
        filename = fs.filename or 'audio'
        ext = os.path.splitext(filename)[1].lower()
        if ext not in ALLOWED_EXTS:
            errors.append(f'{filename}: unsupported format ({ext or "unknown"}). '
                          f'Supported: {", ".join(sorted(ALLOWED_EXTS))}')
            continue

        from .links import uuid_name
        stored = uuid_name(ext)
        dest = os.path.join(upload_dir, stored)
        fs.save(dest)

        try:
            meta = extract_metadata(dest)
        except Exception:
            try:
                os.remove(dest)
            except OSError:
                pass
            errors.append(f'{filename}: could not read this as an audio file.')
            continue

        fields = _finalize_metadata(meta, filename)
        song = Song(user_id=user.id, source='upload', file_path=f'uploads/{stored}',
                    original_name=os.path.basename(filename)[:255], **fields)
        if meta.get('cover'):
            try:
                song.cover_path = save_cover(meta['cover'][0], meta['cover'][1], cover_dir)
            except Exception:
                song.cover_path = None
        db.session.add(song)
        created.append(song)

    db.session.commit()
    return jsonify(songs=[s.to_dict() for s in created], errors=errors)


@uploads_bp.post('/api/import/preview')
@login_required
def import_preview(user):
    data = request.get_json(silent=True) or {}
    url = (data.get('url') or '').strip()
    kind, info = classify(url)
    if kind == 'invalid':
        return bad_request(info.get('reason', 'That link is not supported.'))
    if kind == 'audio':
        info['requires_rights'] = True
    return jsonify(kind=kind, info=info, url=url)


@uploads_bp.post('/api/import/confirm')
@login_required
def import_confirm(user):
    data = request.get_json(silent=True) or {}
    url = (data.get('url') or '').strip()
    rights = bool(data.get('rights_confirmed'))
    overrides = {
        'title': (data.get('title') or '').strip() or None,
        'artist': (data.get('artist') or '').strip() or None,
        'album': (data.get('album') or '').strip() or None,
        'genre': (data.get('genre') or '').strip() or None,
    }

    kind, info = classify(url)
    if kind == 'invalid':
        return bad_request(info.get('reason', 'That link is not supported.'))

    cover_dir = current_app.config['COVER_DIR']
    song = None

    if kind in ('youtube', 'soundcloud'):
        # Official embed only — we never download or store the media itself.
        song = Song(
            user_id=user.id,
            source=kind,
            title=overrides['title'] or info.get('title') or f'{kind.title()} track',
            artist=overrides['artist'] or info.get('artist') or ('YouTube' if kind == 'youtube' else 'SoundCloud'),
            album=overrides['album'] or '',
            genre=overrides['genre'] or 'External',
            duration=0.0,
            embed_url=info.get('embed_url'),
            external_url=url,
        )
        art = fetch_image(info.get('thumbnail'))
        if art:
            try:
                song.cover_path = save_cover(art, 'image/jpeg', cover_dir)
            except Exception:
                song.cover_path = None

    elif kind == 'audio':
        if not rights:
            return jsonify(error='Please confirm you have the rights to download and keep this audio.'), 403
        upload_dir = current_app.config['UPLOAD_DIR']
        try:
            path, stored = download_audio(url, upload_dir)
        except Exception as e:
            return bad_request(f'Download failed: {e}')
        try:
            meta = extract_metadata(path)
        except Exception:
            os.remove(path)
            return bad_request('That URL did not download into a valid audio file.')
        fields = _finalize_metadata(meta, info.get('filename') or url, overrides)
        song = Song(user_id=user.id, source='download', file_path=f'uploads/{stored}',
                    external_url=url, original_name=(info.get('filename') or '')[:255], **fields)
        if meta.get('cover'):
            try:
                song.cover_path = save_cover(meta['cover'][0], meta['cover'][1], cover_dir)
            except Exception:
                song.cover_path = None

    db.session.add(song)
    db.session.commit()
    return jsonify(song=song.to_dict(),
                   note='Plays through the official embed — nothing was downloaded.'
                   if kind in ('youtube', 'soundcloud') else 'Downloaded and added to your library.')
