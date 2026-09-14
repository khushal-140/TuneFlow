"""Songs: search / filter / sort, likes, play history, audio streaming, recommendations."""
import os

from flask import Blueprint, jsonify, request, send_file

from .extensions import db
from .helpers import bad_request, iso, login_required
from .models import Like, PlayHistory, Playlist, Song, playlist_songs
from .recommender import recommend_for_user

library_bp = Blueprint('library', __name__)

SORTABLE = {
    'title': Song.title,
    'artist': Song.artist,
    'album': Song.album,
    'genre': Song.genre,
    'duration': Song.duration,
    'play_count': Song.play_count,
    'created_at': Song.created_at,
}


def _liked_ids(user_id):
    return {row[0] for row in db.session.query(Like.song_id).filter_by(user_id=user_id)}


def _songs_payload(songs, liked):
    return [s.to_dict(liked=s.id in liked) for s in songs]


def get_owned_song(user, song_id):
    return Song.query.filter_by(id=song_id, user_id=user.id).first()


@library_bp.get('/api/songs')
@login_required
def list_songs(user):
    q = (request.args.get('q') or '').strip()
    genre = (request.args.get('genre') or '').strip()
    artist = (request.args.get('artist') or '').strip()
    sort = request.args.get('sort') or 'created_at'
    order = request.args.get('order') or ('asc' if sort in ('title', 'artist', 'album', 'genre') else 'desc')
    liked_only = request.args.get('liked') == '1'

    query = Song.query.filter_by(user_id=user.id)
    if q:
        like = f'%{q}%'
        query = query.filter(
            (Song.title.ilike(like)) | (Song.artist.ilike(like))
            | (Song.album.ilike(like)) | (Song.genre.ilike(like))
        )
    if genre:
        query = query.filter(db.func.lower(Song.genre) == genre.lower())
    if artist:
        query = query.filter(Song.artist.ilike(f'%{artist}%'))

    col = SORTABLE.get(sort, Song.created_at)
    query = query.order_by(db.asc(col) if order == 'asc' else db.desc(col))

    if liked_only:
        query = query.join(Like, (Like.song_id == Song.id) & (Like.user_id == user.id))

    songs = query.all()
    liked = _liked_ids(user.id)
    return jsonify(songs=_songs_payload(songs, liked), total=len(songs))


@library_bp.get('/api/songs/facets')
@login_required
def facets(user):
    songs = Song.query.filter_by(user_id=user.id).all()
    genres, artists = {}, {}
    for s in songs:
        if s.genre:
            key = s.genre.strip()
            genres[key.lower()] = key
        if s.artist:
            key = s.artist.strip()
            artists[key.lower()] = key
    return jsonify(genres=sorted(genres.values(), key=str.lower), artists=sorted(artists.values(), key=str.lower))


@library_bp.patch('/api/songs/<int:song_id>')
@login_required
def update_song(user, song_id):
    song = get_owned_song(user, song_id)
    if song is None:
        return jsonify(error='Song not found.'), 404
    data = request.get_json(silent=True) or {}
    title = (data.get('title') or '').strip()
    if not title:
        return bad_request('Title cannot be empty.')
    song.title = title[:255]
    song.artist = (data.get('artist') or '').strip()[:255]
    song.album = (data.get('album') or '').strip()[:255]
    song.genre = (data.get('genre') or '').strip()[:64]
    db.session.commit()
    return jsonify(song=song.to_dict(liked=song.id in _liked_ids(user.id)))


@library_bp.delete('/api/songs/<int:song_id>')
@login_required
def delete_song(user, song_id):
    song = get_owned_song(user, song_id)
    if song is None:
        return jsonify(error='Song not found.'), 404

    db.session.execute(playlist_songs.delete().where(playlist_songs.c.song_id == song.id))
    Like.query.filter_by(song_id=song.id).delete()
    PlayHistory.query.filter_by(song_id=song.id).delete()
    db.session.delete(song)
    db.session.commit()

    # Remove media from disk (best effort) for locally-held files.
    static_dir = os.path.realpath(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'static'))
    for rel in (song.file_path, song.cover_path):
        if not rel:
            continue
        path = os.path.realpath(os.path.join(static_dir, rel))
        if path.startswith(static_dir + os.sep) and os.path.exists(path):
            try:
                os.remove(path)
            except OSError:
                pass
    return jsonify(ok=True)


@library_bp.post('/api/songs/<int:song_id>/like')
@login_required
def toggle_like(user, song_id):
    song = get_owned_song(user, song_id)
    if song is None:
        return jsonify(error='Song not found.'), 404
    existing = Like.query.filter_by(user_id=user.id, song_id=song.id).first()
    if existing:
        db.session.delete(existing)
        liked = False
    else:
        db.session.add(Like(user_id=user.id, song_id=song.id))
        liked = True
    db.session.commit()
    return jsonify(liked=liked, song_id=song.id)


@library_bp.post('/api/songs/<int:song_id>/play')
@login_required
def record_play(user, song_id):
    song = get_owned_song(user, song_id)
    if song is None:
        return jsonify(error='Song not found.'), 404
    db.session.add(PlayHistory(user_id=user.id, song_id=song.id))
    song.play_count += 1
    db.session.commit()
    return jsonify(ok=True, play_count=song.play_count)


@library_bp.get('/api/songs/<int:song_id>/stream')
@login_required
def stream(user, song_id):
    song = get_owned_song(user, song_id)
    if song is None or not song.file_path:
        return jsonify(error='Audio not available for this track.'), 404
    static_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'static')
    path = os.path.realpath(os.path.join(static_dir, song.file_path))
    if not path.startswith(os.path.realpath(static_dir) + os.sep) or not os.path.exists(path):
        return jsonify(error='Audio file is missing on disk.'), 404
    # conditional=True gives us HTTP Range support so seeking works.
    return send_file(path, conditional=True)


@library_bp.get('/api/likes')
@login_required
def liked_songs(user):
    songs = (Song.query.join(Like, Like.song_id == Song.id)
             .filter(Like.user_id == user.id)
             .order_by(Like.created_at.desc())
             .all())
    return jsonify(songs=_songs_payload(songs, {s.id for s in songs}), total=len(songs))


@library_bp.get('/api/history')
@login_required
def history(user):
    limit = min(request.args.get('limit', 100, type=int) or 100, 500)
    rows = (PlayHistory.query.filter_by(user_id=user.id)
            .order_by(PlayHistory.played_at.desc())
            .limit(limit).all())
    liked = _liked_ids(user.id)
    return jsonify(history=[{
        'id': r.id,
        'played_at': iso(r.played_at),
        'song': r.song.to_dict(liked=r.song_id in liked) if r.song else None,
    } for r in rows])


@library_bp.get('/api/recommendations')
@login_required
def recommendations(user):
    limit = min(request.args.get('limit', 12, type=int) or 12, 40)
    result = recommend_for_user(user.id, limit)
    return jsonify(songs=result['songs'], taste=result['taste'], mode=result['mode'])


@library_bp.get('/api/home')
@login_required
def home_feed(user):
    """Everything the dashboard needs in one round trip."""
    liked_ids = _liked_ids(user.id)
    all_songs = Song.query.filter_by(user_id=user.id).order_by(Song.created_at.desc()).all()

    # Recently played, deduped, most recent first.
    recent = []
    seen = set()
    rows = (PlayHistory.query.filter_by(user_id=user.id)
            .order_by(PlayHistory.played_at.desc()).limit(60).all())
    for r in rows:
        if r.song_id not in seen and r.song:
            seen.add(r.song_id)
            recent.append(r.song)

    total_plays = PlayHistory.query.filter_by(user_id=user.id).count()
    minutes_row = (db.session.query(db.func.coalesce(db.func.sum(Song.duration), 0.0))
                   .join(PlayHistory, PlayHistory.song_id == Song.id)
                   .filter(PlayHistory.user_id == user.id).scalar())
    playlists = Playlist.query.filter_by(user_id=user.id).order_by(Playlist.created_at.desc()).limit(12).all()

    from .playlists import _playlist_summary

    rec = recommend_for_user(user.id, 12)

    top_genres = {}
    for s in all_songs:
        if s.genre:
            top_genres[s.genre.strip()] = top_genres.get(s.genre.strip(), 0) + 1

    return jsonify(
        user=user.to_dict(),
        stats={
            'songs': len(all_songs),
            'playlists': Playlist.query.filter_by(user_id=user.id).count(),
            'liked': len(liked_ids),
            'plays': total_plays,
            'minutes': round((minutes_row or 0) / 60),
        },
        recent=[s.to_dict(liked=s.id in liked_ids) for s in recent[:12]],
        recommended=rec['songs'],
        taste=rec['taste'],
        rec_mode=rec['mode'],
        new_additions=[s.to_dict(liked=s.id in liked_ids) for s in all_songs[:12]],
        playlists=[_playlist_summary(p, liked_ids) for p in playlists],
        top_genres=sorted(top_genres.items(), key=lambda kv: kv[1], reverse=True)[:6],
    )
