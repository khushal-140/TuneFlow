"""Playlists: CRUD + add/remove tracks with stable ordering."""
from flask import Blueprint, jsonify, request

from .extensions import db
from .helpers import bad_request, iso, login_required
from .library import _liked_ids
from .models import Playlist, Song, playlist_songs

playlists_bp = Blueprint('playlists', __name__)


def _playlist_summary(pl, liked):
    rows = db.session.execute(
        playlist_songs.select().where(playlist_songs.c.playlist_id == pl.id)
        .order_by(playlist_songs.c.position)
    ).fetchall()
    song_ids = [r.song_id for r in rows]
    songs = {s.id: s for s in Song.query.filter(Song.id.in_(song_ids))} if song_ids else {}
    ordered = [songs[sid] for sid in song_ids if sid in songs]
    covers = [s.cover_path for s in ordered if s.cover_path][:4]
    return pl.to_dict(
        song_count=len(ordered),
        total_duration=sum(s.duration or 0 for s in ordered),
        covers=[f'/static/{c}' for c in covers],
    )


def _owned_playlist(user, playlist_id):
    return Playlist.query.filter_by(id=playlist_id, user_id=user.id).first()


@playlists_bp.get('/api/playlists')
@login_required
def list_playlists(user):
    liked = _liked_ids(user.id)
    pls = Playlist.query.filter_by(user_id=user.id).order_by(Playlist.created_at.desc()).all()
    return jsonify(playlists=[_playlist_summary(p, liked) for p in pls])


@playlists_bp.post('/api/playlists')
@login_required
def create_playlist(user):
    data = request.get_json(silent=True) or {}
    name = (data.get('name') or '').strip()
    if not name:
        return bad_request('Playlist needs a name.')
    pl = Playlist(user_id=user.id, name=name[:120], description=(data.get('description') or '').strip()[:500])
    db.session.add(pl)
    db.session.commit()
    return jsonify(playlist=_playlist_summary(pl, set()))


@playlists_bp.get('/api/playlists/<int:playlist_id>')
@login_required
def playlist_detail(user, playlist_id):
    pl = _owned_playlist(user, playlist_id)
    if pl is None:
        return jsonify(error='Playlist not found.'), 404
    rows = db.session.execute(
        playlist_songs.select().where(playlist_songs.c.playlist_id == pl.id)
        .order_by(playlist_songs.c.position)
    ).fetchall()
    song_ids = [r.song_id for r in rows]
    songs = {s.id: s for s in Song.query.filter(Song.id.in_(song_ids))} if song_ids else {}
    liked = _liked_ids(user.id)
    tracks = []
    for r in rows:
        s = songs.get(r.song_id)
        if s:
            d = s.to_dict(liked=s.id in liked)
            d['added_at'] = iso(r.added_at)
            tracks.append(d)
    payload = _playlist_summary(pl, liked)
    payload['songs'] = tracks
    return jsonify(playlist=payload)


@playlists_bp.patch('/api/playlists/<int:playlist_id>')
@login_required
def update_playlist(user, playlist_id):
    pl = _owned_playlist(user, playlist_id)
    if pl is None:
        return jsonify(error='Playlist not found.'), 404
    data = request.get_json(silent=True) or {}
    if 'name' in data:
        name = (data.get('name') or '').strip()
        if not name:
            return bad_request('Playlist needs a name.')
        pl.name = name[:120]
    if 'description' in data:
        pl.description = (data.get('description') or '').strip()[:500]
    db.session.commit()
    return jsonify(playlist=_playlist_summary(pl, _liked_ids(user.id)))


@playlists_bp.delete('/api/playlists/<int:playlist_id>')
@login_required
def delete_playlist(user, playlist_id):
    pl = _owned_playlist(user, playlist_id)
    if pl is None:
        return jsonify(error='Playlist not found.'), 404
    db.session.execute(playlist_songs.delete().where(playlist_songs.c.playlist_id == pl.id))
    db.session.delete(pl)
    db.session.commit()
    return jsonify(ok=True)


@playlists_bp.post('/api/playlists/<int:playlist_id>/songs')
@login_required
def add_songs(user, playlist_id):
    pl = _owned_playlist(user, playlist_id)
    if pl is None:
        return jsonify(error='Playlist not found.'), 404
    data = request.get_json(silent=True) or {}
    ids = data.get('song_ids') or ([data.get('song_id')] if data.get('song_id') else [])
    if not ids:
        return bad_request('No songs to add.')

    existing = {r.song_id for r in db.session.execute(
        playlist_songs.select().where(playlist_songs.c.playlist_id == pl.id)).fetchall()}
    max_pos = db.session.execute(
        db.select(db.func.max(playlist_songs.c.position))
        .where(playlist_songs.c.playlist_id == pl.id)
    ).scalar() or 0

    added, skipped = [], []
    owned = {s.id for s in Song.query.filter(Song.id.in_(ids), Song.user_id == user.id)}
    for sid in ids:
        if sid in existing:
            skipped.append(sid)
            continue
        if sid not in owned:
            skipped.append(sid)
            continue
        max_pos += 1
        db.session.execute(playlist_songs.insert().values(
            playlist_id=pl.id, song_id=sid, position=max_pos))
        existing.add(sid)
        added.append(sid)
    db.session.commit()
    return jsonify(added=added, skipped=skipped, playlist=_playlist_summary(pl, _liked_ids(user.id)))


@playlists_bp.delete('/api/playlists/<int:playlist_id>/songs/<int:song_id>')
@login_required
def remove_song(user, playlist_id, song_id):
    pl = _owned_playlist(user, playlist_id)
    if pl is None:
        return jsonify(error='Playlist not found.'), 404
    db.session.execute(playlist_songs.delete().where(
        (playlist_songs.c.playlist_id == pl.id) & (playlist_songs.c.song_id == song_id)))
    # Re-index remaining positions so ordering stays contiguous.
    rows = db.session.execute(
        playlist_songs.select().where(playlist_songs.c.playlist_id == pl.id)
        .order_by(playlist_songs.c.position)).fetchall()
    for i, r in enumerate(rows):
        if r.position != i:
            db.session.execute(playlist_songs.update().where(
                (playlist_songs.c.playlist_id == pl.id) & (playlist_songs.c.song_id == r.song_id)
            ).values(position=i))
    db.session.commit()
    return jsonify(ok=True)
