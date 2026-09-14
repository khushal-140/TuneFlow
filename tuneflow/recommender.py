"""Content-based recommendation engine.

Builds a taste vector for the user over components `genre:<g>` and `artist:<a>`
from their activity (likes weigh most, then plays, then playlist adds), then
scores every candidate song with cosine similarity between the taste vector and
the song's own genre/artist vector. No external services, pure math.
"""
import math
from collections import defaultdict

from .extensions import db
from .models import Like, PlayHistory, Song, playlist_songs, Playlist

LIKE_WEIGHT = 3.0
PLAY_WEIGHT = 1.0
PLAYLIST_WEIGHT = 0.5
MAX_PLAYS_COUNTED = 8


def _genre_key(genre):
    # 'Lo-Fi' and 'Lofi' and 'lo fi' should collapse to the same component.
    return ''.join(ch for ch in (genre or '').lower() if ch.isalnum())


def taste_profile(user_id):
    """Returns ({component: weight}, {component: human label})."""
    weights = defaultdict(float)
    labels = {}

    def add_song(song, w):
        if song.genre:
            key = 'g:' + _genre_key(song.genre)
            weights[key] += w
            labels.setdefault(key, song.genre.strip())
        if song.artist:
            key = 'a:' + song.artist.strip().lower()
            weights[key] += w
            labels.setdefault(key, song.artist.strip())

    liked_ids = [r[0] for r in db.session.query(Like.song_id).filter_by(user_id=user_id)]
    if liked_ids:
        for song in Song.query.filter(Song.id.in_(liked_ids)):
            add_song(song, LIKE_WEIGHT)

    play_counts = (db.session.query(PlayHistory.song_id, db.func.count().label('c'))
                   .filter_by(user_id=user_id).group_by(PlayHistory.song_id).all())
    if play_counts:
        ids = [sid for sid, _ in play_counts]
        songs = {s.id: s for s in Song.query.filter(Song.id.in_(ids))}
        for sid, cnt in play_counts:
            song = songs.get(sid)
            if song:
                add_song(song, PLAY_WEIGHT * min(cnt, MAX_PLAYS_COUNTED))

    playlist_ids = [r[0] for r in db.session.query(Playlist.id).filter_by(user_id=user_id)]
    if playlist_ids:
        rows = db.session.execute(
            playlist_songs.select().where(playlist_songs.c.playlist_id.in_(playlist_ids))
        ).fetchall()
        song_ids = list({r.song_id for r in rows})
        songs = {s.id: s for s in Song.query.filter(Song.id.in_(song_ids))} if song_ids else {}
        for r in rows:
            song = songs.get(r.song_id)
            if song:
                add_song(song, PLAYLIST_WEIGHT)

    return dict(weights), labels


def _song_vector(song):
    comps = []
    if song.genre:
        comps.append(('g:' + _genre_key(song.genre), 1.0))
    if song.artist:
        comps.append(('a:' + song.artist.strip().lower(), 1.0))
    return comps


def _cosine(taste, comps):
    dot = sum(taste[c] * v for c, v in comps if c in taste)
    if dot <= 0:
        return 0.0, None
    n_taste = math.sqrt(sum(w * w for w in taste.values()))
    n_song = math.sqrt(sum(v * v for _, v in comps))
    if n_taste == 0 or n_song == 0:
        return 0.0, None
    best = max((c for c, _ in comps if c in taste), key=lambda c: taste[c])
    return dot / (n_taste * n_song), best


def _reason_for(comp, labels, song):
    if comp and comp.startswith('a:'):
        name = labels.get(comp)
        if name:
            return f'Because you like {name}'
    if comp and comp.startswith('g:'):
        name = labels.get(comp) or song.genre
        if name:
            return f'More {name} for you'
    return 'Matches your taste'


def recommend_for_user(user_id, limit=12):
    taste, labels = taste_profile(user_id)
    all_songs = Song.query.filter_by(user_id=user_id).all()

    if not taste or not all_songs:
        fallback = sorted(all_songs, key=lambda s: (s.play_count, s.created_at), reverse=True)[:limit]
        return {
            'mode': 'cold_start',
            'taste': [],
            'songs': [{**s.to_dict(), 'reason': 'Popular in your library'} for s in fallback],
        }

    liked_ids = {r[0] for r in db.session.query(Like.song_id).filter_by(user_id=user_id)}
    played_ids = {r[0] for r in db.session.query(PlayHistory.song_id).filter_by(user_id=user_id).distinct()}

    fresh = [s for s in all_songs if s.id not in liked_ids and s.id not in played_ids]
    rediscovery = [s for s in all_songs if s.id not in liked_ids and s.id in played_ids]

    candidates = [(s, False) for s in fresh] + [(s, True) for s in rediscovery]

    scored = []
    for song, is_rediscovery in candidates:
        comps = _song_vector(song)
        sim, best = _cosine(taste, comps)
        if sim <= 0:
            continue
        if is_rediscovery:
            sim *= 0.6
        scored.append((sim, song, best))

    scored.sort(key=lambda t: t[0], reverse=True)
    picked = scored[:limit]

    taste_sorted = sorted(taste.items(), key=lambda kv: kv[1], reverse=True)[:6]
    taste_summary = [{'label': labels.get(c, c), 'type': 'artist' if c.startswith('a:') else 'genre', 'weight': round(w, 2)}
                     for c, w in taste_sorted]

    return {
        'mode': 'personalized',
        'taste': taste_summary,
        'songs': [{
            **song.to_dict(),
            'reason': _reason_for(best, labels, song),
            'score': round(sim, 4),
        } for sim, song, best in picked],
    }
