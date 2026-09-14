"""Seed TuneFlow with a demo account and a small demo library.

Every demo track is synthesized on the fly with pure Python (stdlib `wave`) —
original chord progressions, no copyrighted audio. Covers are generated SVGs.
Seeding also creates likes, play history and playlists so the recommendation
engine and the assistant have something to work with on first launch.

Usage:  python seed_data.py [--force]      (--force rebuilds the demo user)
"""
import array
import math
import os
import random
import sys
from datetime import timedelta

from tuneflow import create_app
from tuneflow.extensions import db
from tuneflow.helpers import now_utc
from tuneflow.models import Like, PlayHistory, Playlist, Song, User, playlist_songs

SR = 16000

PROGS = {
    'lofi':       [[57, 60, 64, 67], [53, 57, 60, 64], [60, 64, 67, 71], [55, 59, 62, 65]],
    'classical':  [[60, 64, 67], [57, 60, 64], [53, 57, 60], [55, 59, 62]],
    'ambient':    [[60, 64, 67, 71], [53, 57, 60, 64]],
    'electronic': [[57, 60, 64], [53, 57, 60], [60, 64, 67], [55, 59, 62]],
    'hiphop':     [[57, 60, 64, 67], [50, 53, 57, 60], [52, 55, 59, 62], [50, 53, 57, 60]],
    'rock':       [[45, 52, 57], [41, 48, 53], [48, 55, 60], [43, 50, 55]],
    'rock2':      [[43, 50, 55], [45, 52, 57], [41, 48, 53], [43, 50, 55]],
    'metal':      [[40, 47, 52], [43, 50, 55], [45, 52, 57], [40, 47, 52]],
    'pop':        [[60, 64, 67], [55, 59, 62], [57, 60, 64], [53, 57, 60]],
    'jazz':       [[50, 53, 57, 60], [55, 59, 62, 65], [60, 64, 67, 71], [57, 60, 64, 67]],
    'acoustic':   [[55, 59, 62], [50, 54, 57], [52, 55, 59], [48, 52, 55]],
    'synthwave':  [[57, 60, 64], [53, 57, 60], [60, 64, 67], [55, 59, 62]],
}

TRACKS = [
    dict(title='Midnight Pages', artist='Yuki Ito', album='Cassette Diaries', genre='Lo-Fi',
         style='pluck', wave='triangle', bpm=76, prog='lofi', bars=14, drums='soft', hue=220),
    dict(title='Rain on Windows', artist='Cloud Folder', album='Cassette Diaries', genre='Lo-Fi',
         style='pad', wave='sine', bpm=70, prog='lofi', bars=12, drums='soft', hue=205),
    dict(title='Waltz of the Quiet Hours', artist='Aurora Ensemble', album='Parlour Sessions', genre='Classical',
         style='pluck', wave='triangle', bpm=96, prog='classical', bars=18, drums=None, hue=30),
    dict(title='Slow Tide', artist='Drift Signal', album='Depth Field', genre='Ambient',
         style='pad', wave='sine', bpm=58, prog='ambient', bars=10, drums=None, hue=190),
    dict(title='Neon Circuit', artist='Pulsewave', album='Voltage Bloom', genre='Electronic',
         style='arp', wave='saw', bpm=124, prog='electronic', bars=20, drums='hard', hue=280),
    dict(title='Frequency Ride', artist='Pulsewave', album='Voltage Bloom', genre='Electronic',
         style='arp', wave='saw', bpm=128, prog='pop', bars=24, drums='hard', hue=265),
    dict(title='Concrete Verse', artist='MC Vertex', album='Street Law', genre='Hip-Hop',
         style='pluck', wave='triangle', bpm=90, prog='hiphop', bars=16, drums='hard', hue=350),
    dict(title='Static Horizon', artist='The Voltage', album='Ampersand', genre='Rock',
         style='power', wave='saw', bpm=132, prog='rock', bars=20, drums='hard', hue=0),
    dict(title='Gasoline Heart', artist='The Voltage', album='Ampersand', genre='Rock',
         style='power', wave='saw', bpm=126, prog='rock2', bars=18, drums='hard', hue=15),
    dict(title='Iron Prayer', artist='Nightforge', album='Anvil Hymns', genre='Metal',
         style='power', wave='saw', bpm=148, prog='metal', bars=24, drums='hard', hue=260),
    dict(title='Sugar Static', artist='Mira Bell', album='Glass Candy', genre='Pop',
         style='arp', wave='triangle', bpm=112, prog='pop', bars=20, drums='hard', hue=320),
    dict(title='Blue Corner Booth', artist='The Ella Trio', album='Smoke & Satin', genre='Jazz',
         style='pluck', wave='triangle', bpm=100, prog='jazz', bars=18, drums='soft', hue=40),
    dict(title='Paper Boats', artist='Hollow Pines', album='River Letters', genre='Acoustic',
         style='pluck', wave='triangle', bpm=84, prog='acoustic', bars=14, drums=None, hue=100),
    dict(title='Chrome Sunset', artist='Nightdrive 84', album='Palm & Chrome', genre='Synthwave',
         style='pad', wave='saw', bpm=98, prog='synthwave', bars=16, drums='soft', hue=310),
]


def midi_to_freq(m):
    return 440.0 * (2.0 ** ((m - 69) / 12.0))


def env_pad(t):
    if t < 0.15:
        return t / 0.15
    if t > 0.72:
        return max(0.0, 1 - (t - 0.72) / 0.28) ** 1.5
    return 1.0


def env_pluck(t):
    return math.exp(-t * 5.5)


class Renderer:
    def __init__(self, n_samples):
        self.n = n_samples
        self.buf = array.array('d', bytes(8 * n_samples))

    def add(self, start, dur, freq, vol, wave_type, env):
        i0 = int(start * SR)
        n = int(dur * SR)
        if n <= 0 or freq <= 0:
            return
        w = 2.0 * math.pi * freq / SR
        for i in range(n):
            idx = i0 + i
            if idx >= self.n:
                break
            ph = w * i
            if wave_type == 'sine':
                v = math.sin(ph)
            elif wave_type == 'triangle':
                v = 0.6366 * math.asin(math.sin(ph))
            elif wave_type == 'saw':
                v = 2.0 * ((freq * i / SR) % 1.0) - 1.0
            else:
                v = math.sin(ph)
            self.buf[idx] += v * vol * env(i / n)

    def kick(self, start, vol=0.5):
        i0 = int(start * SR)
        for i in range(int(0.16 * SR)):
            idx = i0 + i
            if idx >= self.n:
                break
            t = i / SR
            f = 110 * math.exp(-t * 18) + 40
            self.buf[idx] += math.sin(2 * math.pi * f * t) * math.exp(-t * 22) * vol

    def hat(self, start, vol=0.05, rng=None):
        i0 = int(start * SR)
        for i in range(int(0.05 * SR)):
            idx = i0 + i
            if idx >= self.n:
                break
            t = i / SR
            self.buf[idx] += (rng.random() * 2 - 1) * math.exp(-t * 80) * vol

    def snare(self, start, vol=0.22, rng=None):
        i0 = int(start * SR)
        for i in range(int(0.15 * SR)):
            idx = i0 + i
            if idx >= self.n:
                break
            t = i / SR
            body = math.sin(2 * math.pi * 190 * t) * 0.4
            self.buf[idx] += ((rng.random() * 2 - 1) * 0.7 + body) * math.exp(-t * 28) * vol


def render_song(path, spec, seed=7):
    rng = random.Random(seed)
    beat = 60.0 / spec['bpm']
    bar = beat * 4
    chords = PROGS[spec['prog']]
    total = int((bar * spec['bars'] + 1.2) * SR)
    r = Renderer(total)
    t = 0.0

    for b in range(spec['bars']):
        chord = chords[b % len(chords)]
        style = spec['style']
        if style == 'pad':
            for note in chord:
                r.add(t, bar * 1.05, midi_to_freq(note), 0.085, spec['wave'], env_pad)
            r.add(t, bar * 1.05, midi_to_freq(chord[0] - 24), 0.14, 'sine', env_pad)
            if rng.random() < 0.5:  # shimmer melody
                r.add(t + bar * rng.uniform(0, 0.5), 1.2, midi_to_freq(rng.choice(chord) + 12), 0.05, 'sine', env_pluck)
        elif style == 'arp':
            seq = chord + [chord[0] + 12]
            step = beat / 2
            for k in range(8):
                r.add(t + k * step, step * 0.95, midi_to_freq(seq[k % len(seq)]), 0.10, spec['wave'], env_pluck)
            for bb in range(4):
                r.add(t + bb * beat, beat * 0.9, midi_to_freq(chord[0] - 24), 0.14, 'triangle', env_pad)
        elif style == 'pluck':
            for off, note in enumerate(chord):
                r.add(t + off * 0.02, 0.7, midi_to_freq(note), 0.10, 'triangle', env_pluck)
                if b % 2 == 1:
                    r.add(t + beat * 2 + off * 0.02, 0.7, midi_to_freq(note), 0.075, 'triangle', env_pluck)
            r.add(t, bar * 0.95, midi_to_freq(chord[0] - 24), 0.13, 'sine', env_pad)
            for k in range(4):
                if rng.random() < 0.45:
                    r.add(t + k * beat + rng.choice([0, beat / 2]), 0.5,
                          midi_to_freq(rng.choice(chord) + 12), 0.07, 'sine', env_pluck)
        elif style == 'power':
            root = chord[0]
            for note in (root, root + 7, root + 12):
                r.add(t, bar * 1.02, midi_to_freq(note), 0.10, 'saw', env_pad)
                r.add(t, bar * 1.02, midi_to_freq(note) * 1.006, 0.05, 'saw', env_pad)
            r.add(t, bar * 0.9, midi_to_freq(root - 12), 0.16, 'triangle', env_pad)

        drums = spec.get('drums')
        if drums:
            r.kick(t)
            r.kick(t + 2 * beat)
            if drums == 'hard':
                r.kick(t + 2.75 * beat, 0.4)
                r.snare(t + beat, rng=rng)
                r.snare(t + 3 * beat, rng=rng)
            for k in range(8):
                r.hat(t + k * beat / 2, 0.05 if drums == 'hard' else 0.022, rng=rng)
        t += bar

    samples = array.array('h', bytes(2 * total))
    for i in range(total):
        samples[i] = int(max(-1.0, min(1.0, math.tanh(r.buf[i] * 1.1) * 0.92)) * 32767)
    import wave
    w = wave.open(path, 'wb')
    w.setnchannels(1)
    w.setsampwidth(2)
    w.setframerate(SR)
    w.writeframes(samples.tobytes())
    w.close()
    return total / SR


def cover_svg(title, genre, hue):
    words = [w for w in title.split() if w[0].isalpha()]
    initials = ''.join(w[0] for w in words[:2]).upper() or 'TF'
    safe_genre = genre.replace('&', '&amp;')
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="512" height="512" viewBox="0 0 512 512">
<defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1">
<stop offset="0" stop-color="hsl({hue},72%,58%)"/><stop offset="1" stop-color="hsl({(hue + 55) % 360},78%,26%)"/>
</linearGradient></defs>
<rect width="512" height="512" fill="url(#g)"/>
<circle cx="256" cy="248" r="176" fill="none" stroke="rgba(255,255,255,0.22)" stroke-width="2"/>
<circle cx="256" cy="248" r="128" fill="none" stroke="rgba(255,255,255,0.3)" stroke-width="2"/>
<circle cx="256" cy="248" r="10" fill="rgba(255,255,255,0.85)"/>
<text x="256" y="286" font-family="Segoe UI, Arial, sans-serif" font-size="132" font-weight="700"
 fill="rgba(255,255,255,0.94)" text-anchor="middle" letter-spacing="4">{initials}</text>
<text x="256" y="440" font-family="Segoe UI, Arial, sans-serif" font-size="24" font-weight="600"
 fill="rgba(255,255,255,0.82)" text-anchor="middle" letter-spacing="8">{safe_genre.upper()}</text>
</svg>'''


HUE_BY_GENRE = {'Lo-Fi': 220, 'Classical': 30, 'Ambient': 190, 'Electronic': 280, 'Hip-Hop': 350,
                'Rock': 0, 'Metal': 260, 'Pop': 320, 'Jazz': 40, 'Acoustic': 100, 'Synthwave': 310}


def slug(name):
    return ''.join(ch if ch.isalnum() else '-' for ch in name.lower()).strip('-')


def main():
    force = '--force' in sys.argv
    app = create_app()
    with app.app_context():
        user = User.query.filter_by(username='demo').first()
        if user and not force:
            print('Demo user already exists — nothing to do. (Use --force to rebuild.)')
            return
        if user:
            for s in Song.query.filter_by(user_id=user.id):
                for rel in (s.file_path, s.cover_path):
                    p = os.path.join(app.static_folder, rel or '')
                    if rel and os.path.exists(p):
                        os.remove(p)
            db.session.delete(user)
            db.session.commit()
            print('Removed previous demo user.')

        user = User(username='demo', email='demo@tuneflow.local')
        user.set_password('demo123')
        db.session.add(user)
        db.session.commit()
        print('Created demo user (demo / demo123).')

        upload_dir = app.config['UPLOAD_DIR']
        cover_dir = app.config['COVER_DIR']
        songs = {}
        for i, spec in enumerate(TRACKS, 1):
            fname = slug(f"{spec['artist']} {spec['title']}") + '.wav'
            path = os.path.join(upload_dir, fname)
            duration = render_song(path, spec, seed=100 + i)
            hue = spec.get('hue', HUE_BY_GENRE.get(spec['genre'], 260))
            cname = slug(f"{spec['artist']} {spec['title']}") + '.svg'
            with open(os.path.join(cover_dir, cname), 'w', encoding='utf-8') as fh:
                fh.write(cover_svg(spec['title'], spec['genre'], hue))
            song = Song(user_id=user.id, title=spec['title'], artist=spec['artist'],
                        album=spec['album'], genre=spec['genre'], duration=round(duration, 2),
                        source='upload', file_path=f'uploads/{fname}', cover_path=f'covers/{cname}',
                        original_name=fname)
            db.session.add(song)
            songs[spec['title']] = song
            print(f'  [{i:>2}/{len(TRACKS)}] rendered {spec["title"]} ({duration:.0f}s)')
        db.session.commit()

        like_titles = ['Midnight Pages', 'Rain on Windows', 'Slow Tide', 'Blue Corner Booth',
                       'Paper Boats', 'Neon Circuit']
        now = now_utc()
        for j, title in enumerate(like_titles):
            db.session.add(Like(user_id=user.id, song_id=songs[title].id,
                                created_at=now - timedelta(days=6 - j // 2)))
        print('Added likes.')

        play_plan = [
            ('Midnight Pages', 4, 6), ('Rain on Windows', 3, 6), ('Slow Tide', 3, 5),
            ('Waltz of the Quiet Hours', 1, 5), ('Neon Circuit', 4, 4), ('Frequency Ride', 2, 3),
            ('Static Horizon', 2, 3), ('Blue Corner Booth', 2, 2), ('Paper Boats', 2, 2),
            ('Sugar Static', 1, 1), ('Chrome Sunset', 1, 1), ('Concrete Verse', 1, 0),
        ]
        rng = random.Random(42)
        for title, plays, days_ago in play_plan:
            song = songs[title]
            for k in range(plays):
                played = now - timedelta(days=rng.uniform(0, days_ago + 0.5),
                                         hours=rng.uniform(0, 10))
                db.session.add(PlayHistory(user_id=user.id, song_id=song.id, played_at=played))
            song.play_count += plays
        db.session.commit()
        print('Added listening history.')

        def make_playlist(name, desc, titles, days_ago):
            pl = Playlist(user_id=user.id, name=name, description=desc,
                          created_at=now - timedelta(days=days_ago))
            db.session.add(pl)
            db.session.flush()
            for pos, title in enumerate(titles):
                db.session.execute(playlist_songs.insert().values(
                    playlist_id=pl.id, song_id=songs[title].id, position=pos,
                    added_at=now - timedelta(days=days_ago)))
            return pl

        make_playlist('Late Night Focus', 'Quiet instrumentals for deep work.',
                      ['Midnight Pages', 'Rain on Windows', 'Slow Tide',
                       'Waltz of the Quiet Hours', 'Paper Boats'], 6)
        make_playlist('Gym Push', 'Loud and fast. No skipping.',
                      ['Neon Circuit', 'Frequency Ride', 'Static Horizon', 'Iron Prayer',
                       'Concrete Verse'], 4)
        make_playlist('Golden Hour', 'Bright, warm, a little shiny.',
                      ['Sugar Static', 'Chrome Sunset', 'Blue Corner Booth'], 2)
        db.session.commit()
        print('Added playlists: Late Night Focus, Gym Push, Golden Hour.')
        total_min = sum(s.duration for s in songs.values()) / 60
        print(f'Done. {len(songs)} tracks (~{total_min:.0f} min) ready for the demo account.')


if __name__ == '__main__':
    main()
