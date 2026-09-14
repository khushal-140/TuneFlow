"""Natural-language intent parsing for the assistant — pure rules, no external AI.

Understands:
  * mood / activity requests   "play something relaxing", "gym music"
  * durations                  "30-minute study playlist", "1 hour of jazz"
  * artists & genres           "play something by Pulsewave", "some lo-fi"
  * free-text search fallback
"""
import random
import re

MOODS = {
    'study': {
        'synonyms': ['study', 'studying', 'focus', 'concentrate', 'homework', 'work', 'reading', 'writing', 'coding'],
        'genres': ['lofi', 'lo fi', 'classical', 'ambient', 'piano', 'acoustic', 'jazz'],
        'keywords': ['study', 'focus', 'quiet', 'calm', 'soft', 'slow', 'rain', 'midnight', 'pages'],
        'name': 'Study Session',
    },
    'gym': {
        'synonyms': ['gym', 'workout', 'working out', 'exercise', 'training', 'lifting', 'pump', 'run', 'running',
                     'jog', 'cardio', 'energy', 'hype', 'power'],
        'genres': ['electronic', 'hiphop', 'hip hop', 'metal', 'rock', 'synthwave', 'funk'],
        'keywords': ['neon', 'iron', 'voltage', 'fast', 'power', 'frequency', 'circuit'],
        'name': 'Gym Fuel',
    },
    'chill': {
        'synonyms': ['relax', 'relaxing', 'relaxed', 'chill', 'chilling', 'calm', 'sleep', 'sleepy', 'unwind',
                     'peaceful', 'cozy', 'mellow', 'laid back', 'chilled'],
        'genres': ['lofi', 'lo fi', 'ambient', 'jazz', 'acoustic', 'classical'],
        'keywords': ['slow', 'tide', 'rain', 'quiet', 'sunset', 'booth', 'soft'],
        'name': 'Chill Mix',
    },
    'party': {
        'synonyms': ['party', 'dance', 'dancing', 'club', 'rave', 'turn up', 'celebrate'],
        'genres': ['electronic', 'pop', 'funk', 'hiphop', 'hip hop', 'dance'],
        'keywords': ['groove', 'motion', 'static', 'sugar', 'neon'],
        'name': 'Party Starters',
    },
    'sad': {
        'synonyms': ['sad', 'crying', 'cry', 'heartbreak', 'breakup', 'down', 'melancholy', 'emotional', 'moody'],
        'genres': ['acoustic', 'classical', 'lofi', 'lo fi', 'ambient'],
        'keywords': ['rain', 'paper', 'boats', 'letters', 'prayer'],
        'name': 'Rainy Night',
    },
    'happy': {
        'synonyms': ['happy', 'upbeat', 'cheerful', 'cheer', 'joy', 'good mood', 'bright', 'sunny', 'summer'],
        'genres': ['pop', 'funk', 'disco', 'synthwave'],
        'keywords': ['sugar', 'sun', 'bloom', 'candy'],
        'name': 'Feel-Good Mix',
    },
    'drive': {
        'synonyms': ['drive', 'driving', 'roadtrip', 'road trip', 'highway', 'car', 'night drive', 'cruise'],
        'genres': ['rock', 'synthwave', 'electronic', 'metal'],
        'keywords': ['chrome', 'sunset', 'horizon', 'ride', 'gasoline'],
        'name': 'Night Drive',
    },
    'romance': {
        'synonyms': ['romantic', 'romance', 'love', 'date', 'dinner', 'slow dance'],
        'genres': ['jazz', 'acoustic', 'rnb', 'soul', 'classical'],
        'keywords': ['booth', 'blue', 'boats', 'velvet'],
        'name': 'Slow Dance',
    },
}

# synonym phrase -> mood key (longest phrases first at match time)
SYNONYM_INDEX = {}
for mood_key, spec in MOODS.items():
    for syn in spec['synonyms']:
        SYNONYM_INDEX[syn] = mood_key

FILLER = {
    'play', 'some', 'something', 'anything', 'music', 'song', 'songs', 'track', 'tracks', 'make', 'me', 'a', 'an',
    'the', 'please', 'playlist', 'with', 'for', 'of', 'about', 'like', 'by', 'get', 'create', 'build', 'want',
    'i', 'to', 'listen', 'and', 'give', 'find', 'need', 'nice', 'good', 'few', 'bunch', 'that', 'this', 'my',
    'can', 'you', 'would', 'could', 'put', 'on', 'up', 'hour', 'hours', 'minutes', 'minute', 'mins', 'min', 'hrs', 'hr', 'h',
}

MIN_RE = re.compile(r'(\d+)\s*(?:-|\s)?\s*(minutes?|mins?|m)\b', re.I)
HOUR_RE = re.compile(r'(\d+)\s*(?:-|\s)?\s*(hours?|hrs?|h)\b', re.I)
BY_ARTIST_RE = re.compile(r'\b(?:by|from|like)\s+([a-z0-9 &\'\.-]+)', re.I)


def _norm(s):
    return ''.join(ch for ch in (s or '').lower() if ch.isalnum())


def parse(message):
    text = (message or '').lower().strip()
    parsed = {
        'mood': None, 'minutes': None, 'artists': [], 'genres': [],
        'keywords': [], 'search': None, 'playlist_name': None,
    }

    m = HOUR_RE.search(text)
    if m:
        parsed['minutes'] = int(m.group(1)) * 60
    m2 = MIN_RE.search(text)
    if m2:
        mins = int(m2.group(1))
        if parsed['minutes'] and parsed['minutes'] % 60 == 0 and mins < 60:
            parsed['minutes'] += 0  # "1 hour 30" handled below
        if parsed['minutes'] is None or mins < parsed['minutes']:
            base = (parsed['minutes'] // 60 * 60) if (parsed['minutes'] and parsed['minutes'] >= 60) else 0
            parsed['minutes'] = base + mins
    if parsed['minutes'] and parsed['minutes'] <= 0:
        parsed['minutes'] = None

    # Mood: longest synonym match wins.
    best_syn, best_len = None, 0
    for syn, mood_key in SYNONYM_INDEX.items():
        if re.search(r'\b' + re.escape(syn) + r'\b', text) and len(syn) > best_len:
            best_syn, best_len = syn, len(syn)
    if best_syn:
        parsed['mood'] = SYNONYM_INDEX[best_syn]
        spec = MOODS[parsed['mood']]
        name = spec['name']
        parsed['playlist_name'] = (f'{parsed["minutes"]}-min ' if parsed['minutes'] else '') + name

    # Artists mentioned verbatim ("by <name>" handled by caller against the library).
    for m3 in BY_ARTIST_RE.finditer(text):
        candidate = m3.group(1).strip()
        candidate = re.split(r'\b(?:please|and|or|that|this|playlist|music|songs?)\b', candidate)[0].strip()
        if candidate and candidate not in parsed['artists']:
            parsed['artists'].append(candidate)

    # Generic keyword leftovers for scoring.
    words = re.findall(r"[a-z0-9']+", text)
    leftovers = [w for w in words if w not in FILLER and not w.isdigit()]
    parsed['keywords'] = leftovers

    if leftovers:
        parsed['search'] = ' '.join(leftovers)
    return parsed


def match_library(parsed, songs):
    """Score every library song against the parsed request. Returns ranked songs."""
    import random as _r

    rng = _r.Random()

    def genre_tokens(g):
        n = _norm(g)
        return {n, n.replace('lofi', 'lo fi')} | ({n} if n else set())

    def matches_mood_genre(song_genre, mood):
        if not song_genre or not mood:
            return False
        ng = _norm(song_genre)
        return any(_norm(t) and (_norm(t) in ng or ng in _norm(t)) for t in MOODS[mood]['genres'])

    scored = []
    for s in songs:
        score = 0.0
        title = (s.title or '').lower()
        album = (s.album or '').lower()
        artist = (s.artist or '').lower()
        genre = (s.genre or '').lower()

        if parsed['mood']:
            spec = MOODS[parsed['mood']]
            if matches_mood_genre(genre, parsed['mood']):
                score += 14
            for kw in spec['keywords']:
                if kw in title or kw in album or kw in genre:
                    score += 6
        for a in parsed['artists']:
            an = _norm(a)
            if an and (an == _norm(artist) or an in _norm(artist) or _norm(artist) in an):
                score += 50
        for g in parsed['genres']:
            gn = _norm(g)
            if gn and (gn in _norm(genre) or _norm(genre) in gn):
                score += 20
        for kw in parsed['keywords']:
            if kw in title or kw in album:
                score += 4
            elif kw in artist or kw in genre:
                score += 2
        score += min(s.play_count, 10) * 0.1
        # tiebreak randomly so repeated asks feel alive
        scored.append((score, rng.random(), s))

    scored.sort(key=lambda t: (t[0], t[1]), reverse=True)
    return [s for score, _, s in scored if score > 0], scored


def build_reply(parsed, picked, total_seconds, shortfall=False):
    if not picked:
        return ("I couldn't find matching tracks in your library yet. Upload a few songs or import some, "
                "then ask me again — I only search what you own.")
    n = len(picked)
    if parsed['minutes']:
        mins = round(total_seconds / 60)
        lead = f"Here's a {mins}-minute {parsed['playlist_name'] or 'playlist'}"
        if shortfall:
            lead = (f"Your library only had {mins} minutes of matches, so here's everything that fits — "
                    f"{n} track{'s' if n != 1 else ''}. Add more music and I can stretch it further.")
        else:
            lead += f" — {n} track{'s' if n != 1 else ''}, tuned to your request."
        return lead + ' Want it as a playlist? Hit save below.'
    if parsed['mood']:
        return f"Here are {n} {MOODS[parsed['mood']]['name'].lower()} track{'s' if n != 1 else ''} from your library. Hit play, or save them as a playlist."
    if parsed['artists']:
        return f"Found {n} track{'s' if n != 1 else ''} matching those artists in your library."
    if parsed['search']:
        return f"Best matches in your library for \u201c{parsed['search']}\u201d."
    return f"Here's what I found — {n} track{'s' if n != 1 else ''}."
