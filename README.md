# TuneFlow 🎵

A **self-hosted, personal music streaming platform** — like running your own private Spotify.
Flask + SQLAlchemy + SQLite on the backend, vanilla HTML/CSS/JS on the frontend, dark premium UI.

## Features

| Area | What it does |
|---|---|
| **Auth + dashboard** | Register / sign in (session-based), home feed with recently played, "Made for you", playlists, stats and quick actions |
| **Music library** | Server-side search, genre/artist filters, sorting, and a fully working audio player (queue, shuffle, repeat, seek, volume, media keys) |
| **Playlists / likes / history** | Create & reorder playlists, heart songs, and every play is logged and shown in History |
| **Smart upload** | Drop an audio file — Mutagen extracts title / artist / album / genre / duration **and embedded cover art**; edit anything before saving |
| **Smart link import** | YouTube & SoundCloud links play through their **official embeds** (nothing is downloaded or pirated); direct audio URLs are downloaded only after you confirm you have the rights |
| **AI assistant** | Chat like "make me a 30-minute study playlist" — a rule-based NLU parses moods, activities, durations and artists and searches **only your library**. No external AI APIs. |
| **Recommendation engine** | Content-based: builds a taste vector from likes (weight 3), plays (weight 1, capped) and playlist adds (weight 0.5) over genre/artist components, then ranks unseen tracks by **cosine similarity** — with a human-readable "because you like…" reason |

## Quickstart

Requires Python 3.10+.

```bash
cd TuneFlow

# 1. create a virtualenv
python -m venv .venv
# Windows (Git Bash / PowerShell):
.venv/Scripts/python -m pip install -r requirements.txt
# macOS / Linux:
# .venv/bin/python -m pip install -r requirements.txt

# 2. (optional but recommended) seed a demo account + 14 synthesized demo tracks
.venv/Scripts/python seed_data.py          # add --force to rebuild

# 3. run
.venv/Scripts/python run.py
```

Open **http://127.0.0.1:5000** and sign in with the demo account:

- username: `demo`
- password: `demo123`

> Seeding synthesizes ~10 minutes of original royalty-free audio with pure Python
> (no copyrighted material, no ffmpeg needed) and takes up to a couple of minutes.

Without seeding you get a fresh empty account — use **Upload** or **Import link** to fill your library.

## How the smart parts work

### Metadata extraction (`tuneflow/metadata.py`)
Mutagen reads tags (ID3 / MP4 / FLAC / Vorbis / WAVE) plus embedded cover art from
`APIC`, `covr`, FLAC `Picture` blocks and Ogg `metadata_block_picture`. Missing tags
fall back to `Artist - Title.ext` filename parsing. Cover art is stored under
`static/covers/`, audio under `static/uploads/` and streamed with HTTP Range support.

### Link import (`tuneflow/links.py`)
- **YouTube / SoundCloud** → resolved via their public oEmbed APIs and stored as
  official embed URLs (privacy-friendly `youtube-nocookie` player). The media is
  never downloaded — playback happens in their player, inside TuneFlow's player bar.
- **Direct audio URL** → headers are inspected first (type/size preview); the download
  only proceeds when you tick the rights confirmation (enforced server-side too).

### Assistant NLU (`tuneflow/nlu.py`)
Pure rules: longest-synonym mood matching (study / gym / chill / party / sad / happy /
drive / romance), duration regexes ("30-minute", "1 hour"), verbatim artist/genre
matching against *your* library, then keyword scoring with a randomized tiebreak.
Durations make it greedily fill a playlist up to the requested length. One click saves
any answer as a real playlist.

### Recommender (`tuneflow/recommender.py`)
1. Build a weighted taste vector: `genre:<g>` and `artist:<a>` components from likes,
   play history and playlist membership.
2. Every candidate song (not liked, not yet played) becomes its own genre+artist vector.
3. Score = cosine similarity between taste vector and song vector; already-played songs
   are allowed back as "rediscovery" at 0.6× weight.
4. Cold start (no activity) falls back to most-played / recently added.

## Project layout

```
TuneFlow/
├── run.py                  # entry point
├── seed_data.py            # demo account + synthesized demo tracks
├── requirements.txt
├── tuneflow/
│   ├── __init__.py         # app factory, blueprints, error handlers
│   ├── extensions.py       # SQLAlchemy instance
│   ├── models.py           # User, Song, Playlist, Like, PlayHistory
│   ├── helpers.py          # auth guard, current user
│   ├── auth.py             # /api/auth/*
│   ├── library.py          # /api/songs*, /api/likes, /api/history, /api/home, /api/recommendations
│   ├── playlists.py        # /api/playlists*
│   ├── uploads.py          # /api/upload, /api/import/*
│   ├── ai.py               # /api/assistant*
│   ├── metadata.py         # Mutagen extraction
│   ├── links.py            # YouTube / SoundCloud / direct-audio logic
│   ├── nlu.py              # assistant language parsing
│   └── recommender.py      # cosine-similarity engine
├── templates/index.html    # SPA shell
└── static/
    ├── css/style.css       # dark premium design system
    ├── js/                 # vanilla ES modules (router, player, views…)
    ├── uploads/            # your audio files
    └── covers/             # extracted / generated cover art
```

## API sketch (all JSON, session-authenticated)

```
POST /api/auth/register | login | logout      GET /api/me
GET  /api/songs?q&genre&artist&sort&order     GET /api/songs/facets
PATCH|DELETE /api/songs/<id>                  GET /api/songs/<id>/stream
POST /api/songs/<id>/like  (toggle)           POST /api/songs/<id>/play
GET  /api/likes                               GET /api/history
GET/POST /api/playlists                       GET|PATCH|DELETE /api/playlists/<id>
POST /api/playlists/<id>/songs                DELETE /api/playlists/<id>/songs/<sid>
POST /api/upload                              POST /api/import/preview | confirm
GET  /api/recommendations                     POST /api/assistant
GET  /api/home                                GET /api/health
```

## Notes

- **Rights**: TuneFlow never ships music. Uploads are your own files; embeds use the
  platforms' official players; direct downloads require an explicit confirmation.
- **Dev scripts**: `scripts/smoke_test.py` exercises the whole API end-to-end
  (run it while the server is up: `.venv/Scripts/python scripts/smoke_test.py`).
- Database lives in `instance/tuneflow.db`; delete it (and `--force` reseed) for a reset.
- If port 5000 is taken: `PORT=5050 .venv/Scripts/python run.py`.
