"""Audio metadata extraction via Mutagen: tags + embedded cover art + duration."""
import base64
import os
import uuid

from mutagen import File as MutagenFile

ALLOWED_EXTS = {'.mp3', '.m4a', '.mp4', '.flac', '.wav', '.ogg', '.oga', '.opus', '.aac', '.wma'}

_MIME_EXT = {'image/jpeg': 'jpg', 'image/png': 'png', 'image/gif': 'gif', 'image/webp': 'webp'}


def sniff_image_mime(data):
    if data[:8] == b'\x89PNG\r\n\x1a\n':
        return 'image/png'
    if data[:3] == b'\xff\xd8\xff':
        return 'image/jpeg'
    if data[:4] == b'GIF8':
        return 'image/gif'
    if data[:4] == b'RIFF' and data[8:12] == b'WEBP':
        return 'image/webp'
    return 'image/jpeg'


def _pictures(mutagen_file):
    """Collect embedded cover art from any tag format Mutagen understands."""
    pics = []
    tags = getattr(mutagen_file, 'tags', None)
    if tags is None:
        return pics

    # ID3 (MP3, WAV, AAC-in-ID3): APIC frames
    try:
        pics.extend(tags.getall('APIC'))
    except Exception:
        pass

    # MP4 / M4A: 'covr' box of MP4Cover (a bytes subclass)
    try:
        covr = tags.get('covr')
        if covr:
            pics.extend(covr)
    except Exception:
        pass

    # FLAC: native Picture blocks
    for p in (getattr(mutagen_file, 'pictures', None) or []):
        pics.append(p)

    # Ogg Vorbis / Opus: base64-encoded FLAC pictures in metadata_block_picture
    try:
        for b64 in (tags.get('metadata_block_picture') or []):
            from mutagen.flac import Picture
            pics.append(Picture(base64.b64decode(b64)))
    except Exception:
        pass

    return pics


def _load_any(path):
    """Load a raw (non-easy) mutagen file object, surviving detection quirks.

    Some WAV taggers (including mutagen's own WAVE.save) prepend a raw ID3
    chunk before the RIFF header, which makes mutagen.File() mis-detect the
    file as MP3. We fall back to stripping that chunk and parsing explicitly.
    """
    from mutagen import File as MutagenFile
    try:
        f = MutagenFile(path)
        if f is not None and f.info is not None:
            return f
    except Exception:
        pass
    try:
        with open(path, 'rb') as fh:
            head = fh.read(10)
            if head.startswith(b'ID3'):
                size = 0
                for byte in head[6:10]:
                    size = (size << 7) | (byte & 0x7F)
                id3_block = head + fh.read(size)
                rest = fh.read()
            else:
                return None
        import tempfile
        fd, tmp = tempfile.mkstemp(suffix='.wav')
        with os.fdopen(fd, 'wb') as out:
            out.write(rest)
        try:
            import mutagen.wave
            f = mutagen.wave.WAVE(tmp)
            if f is not None and f.info is not None:
                if not f.tags:
                    # Re-attach the ID3 chunk we stripped off the front.
                    try:
                        import io
                        from mutagen.id3 import ID3 as _ID3
                        f.tags = _ID3(fileobj=io.BytesIO(id3_block))
                    except Exception:
                        pass
                return f
        finally:
            try:
                os.remove(tmp)
            except OSError:
                pass
    except Exception:
        pass
    return None


_ID3_FRAME_IDS = {'title': 'TIT2', 'artist': 'TPE1', 'album': 'TALB', 'genre': 'TCON'}


def _tag_first(tags, key):
    """Read a text tag from either EasyID3-style tags or real ID3 frames."""
    if tags is None:
        return None
    try:
        v = tags.get(key)
        if v:
            s = str(v[0]).strip()
            if s:
                return s
    except Exception:
        pass
    fid = _ID3_FRAME_IDS.get(key)
    if fid:
        try:
            v = tags.getall(fid)
            if v:
                s = str(v[0]).strip()
                if s:
                    return s
        except Exception:
            pass
    return None


def extract_metadata(path):
    """Returns dict(title, artist, album, genre, duration, cover=(bytes, mime) | None).

    Raises ValueError when the file is not recognizable audio.
    """
    f = None
    try:
        from mutagen import File as MutagenFile
        f = MutagenFile(path, easy=True)
    except Exception:
        f = None
    if f is None or f.info is None:
        f = _load_any(path)
    if f is None or f.info is None:
        raise ValueError('Not a recognized audio file.')

    tags = f.tags
    meta = {
        'title': _tag_first(tags, 'title'),
        'artist': _tag_first(tags, 'artist'),
        'album': _tag_first(tags, 'album'),
        'genre': _tag_first(tags, 'genre'),
        'duration': float(f.info.length or 0.0),
        'cover': None,
    }

    try:
        g = _load_any(path)
        pics = _pictures(g) if g else []
        if pics:
            best = max(pics, key=lambda p: len(getattr(p, 'data', b'') or bytes(p) or b''))
            data = getattr(best, 'data', None) or bytes(best)
            if data:
                mime = getattr(best, 'mime', None) or sniff_image_mime(data)
                if mime not in _MIME_EXT:  # some taggers write odd mime strings
                    mime = sniff_image_mime(data)
                meta['cover'] = (data, mime)
    except Exception:
        meta['cover'] = None

    return meta


def save_cover(data, mime, cover_dir):
    ext = _MIME_EXT.get(mime, 'jpg')
    name = uuid.uuid4().hex + '.' + ext
    path = os.path.join(cover_dir, name)
    with open(path, 'wb') as fh:
        fh.write(data)
    return 'covers/' + name


def title_from_filename(filename):
    """Fallback parse: 'Artist - Title.mp3' -> ('Artist', 'Title')."""
    stem = os.path.splitext(os.path.basename(filename))[0].strip()
    if ' - ' in stem:
        artist, title = stem.split(' - ', 1)
        return title.strip() or stem, artist.strip()
    return stem, ''
