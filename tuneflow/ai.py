"""Assistant endpoints: chat-style natural language search over the user's own library."""
import random

from flask import Blueprint, jsonify, request

from .extensions import db
from .helpers import bad_request, login_required
from .library import _liked_ids
from .models import Song
from .nlu import build_reply, match_library, parse

ai_bp = Blueprint('ai', __name__)


@ai_bp.get('/api/assistant/examples')
@login_required
def examples(user):
    base = [
        'Make me a 30-minute study playlist',
        'Play something relaxing',
        'Gym music, high energy',
        'Sad songs for a rainy night',
        'Upbeat tracks for a morning run',
        'Chill vibes for late night coding',
    ]
    artists = [s.artist for s in Song.query.filter_by(user_id=user.id).all() if s.artist]
    artists = sorted(set(a.strip() for a in artists))
    if artists:
        rng = random.Random()
        for name in rng.sample(artists, min(2, len(artists))):
            base.append(f'Play something by {name}')
    return jsonify(examples=base)


@ai_bp.post('/api/assistant')
@login_required
def ask(user):
    data = request.get_json(silent=True) or {}
    message = (data.get('message') or '').strip()
    if not message:
        return bad_request('Say something like "make me a 30-minute study playlist".')

    parsed = parse(message)
    songs = Song.query.filter_by(user_id=user.id).all()
    if not songs:
        return jsonify(
            reply='Your library is empty, so I have nothing to search yet. Upload some audio or import a link, '
                  'and then I can build playlists from it.',
            tracks=[], intent=parsed, playlist_name=None)

    ranked, all_scored = match_library(parsed, songs)
    liked = _liked_ids(user.id)

    def out(song):
        return song.to_dict(liked=song.id in liked)

    shortfall = False
    if parsed['minutes']:
        target = parsed['minutes'] * 60
        picked, total = [], 0.0
        for s in ranked:
            dur = s.duration or 0
            if total + dur > target * 1.15:
                continue
            picked.append(s)
            total += dur
            if total >= target:
                break
        if total < target * 0.8:
            shortfall = True
        if not picked and ranked:
            picked = ranked[:5]
            total = sum(s.duration or 0 for s in picked)
        return jsonify(
            reply=build_reply(parsed, picked, total, shortfall),
            tracks=[out(s) for s in picked],
            intent={'mood': parsed['mood'], 'minutes': parsed['minutes'],
                    'artists': parsed['artists'], 'genres': parsed['genres']},
            playlist_name=parsed.get('playlist_name') or 'My Mix',
            total_duration=round(total, 1))

    picked = ranked[:12] if ranked else [s for _, _, s in sorted(all_scored, key=lambda t: t[0], reverse=True)[:6]]
    total = sum(s.duration or 0 for s in picked)
    return jsonify(
        reply=build_reply(parsed, picked, total),
        tracks=[out(s) for s in picked],
        intent={'mood': parsed['mood'], 'minutes': parsed['minutes'],
                'artists': parsed['artists'], 'genres': parsed['genres']},
        playlist_name=parsed.get('playlist_name') or 'My Mix',
        total_duration=round(total, 1))
