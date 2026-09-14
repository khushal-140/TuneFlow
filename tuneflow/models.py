from .extensions import db
from .timeutil import iso, now_utc


class User(db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(32), unique=True, nullable=False, index=True)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=now_utc, nullable=False)

    songs = db.relationship('Song', backref='owner', lazy='dynamic', cascade='all, delete-orphan')
    playlists = db.relationship('Playlist', backref='owner', lazy='dynamic', cascade='all, delete-orphan')

    def set_password(self, password):
        from werkzeug.security import generate_password_hash
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        from werkzeug.security import check_password_hash
        return check_password_hash(self.password_hash, password)

    def to_dict(self):
        return {
            'id': self.id,
            'username': self.username,
            'email': self.email,
            'created_at': iso(self.created_at),
        }


class Song(db.Model):
    __tablename__ = 'songs'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    title = db.Column(db.String(255), nullable=False)
    artist = db.Column(db.String(255), default='', nullable=False)
    album = db.Column(db.String(255), default='', nullable=False)
    genre = db.Column(db.String(64), default='', nullable=False, index=True)
    duration = db.Column(db.Float, default=0.0, nullable=False)  # seconds, 0 = unknown (embeds)
    source = db.Column(db.String(16), nullable=False, default='upload')
    # 'upload' = file uploaded, 'download' = direct audio URL downloaded,
    # 'youtube' / 'soundcloud' = official embed, never downloaded.
    file_path = db.Column(db.String(255))      # relative to /static, e.g. uploads/abc.mp3
    cover_path = db.Column(db.String(255))     # relative to /static, e.g. covers/abc.jpg
    embed_url = db.Column(db.String(512))
    external_url = db.Column(db.String(1024))
    original_name = db.Column(db.String(255))
    play_count = db.Column(db.Integer, default=0, nullable=False)
    created_at = db.Column(db.DateTime, default=now_utc, nullable=False)

    def to_dict(self, liked=False):
        return {
            'id': self.id,
            'title': self.title,
            'artist': self.artist or '',
            'album': self.album or '',
            'genre': self.genre or '',
            'duration': round(self.duration or 0, 2),
            'source': self.source,
            'cover': f'/static/{self.cover_path}' if self.cover_path else None,
            'stream': f'/api/songs/{self.id}/stream' if self.file_path else None,
            'embed_url': self.embed_url,
            'external_url': self.external_url,
            'play_count': self.play_count,
            'liked': bool(liked),
            'created_at': iso(self.created_at),
        }


class Playlist(db.Model):
    __tablename__ = 'playlists'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    name = db.Column(db.String(120), nullable=False)
    description = db.Column(db.String(500), default='', nullable=False)
    created_at = db.Column(db.DateTime, default=now_utc, nullable=False)

    def to_dict(self, song_count=0, total_duration=0.0, covers=None):
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description or '',
            'song_count': song_count,
            'total_duration': round(total_duration, 2),
            'covers': covers or [],
            'created_at': iso(self.created_at),
        }


# Association table with ordering info (extra columns, so plain Table + manual inserts).
playlist_songs = db.Table(
    'playlist_songs',
    db.Column('playlist_id', db.Integer, db.ForeignKey('playlists.id'), primary_key=True),
    db.Column('song_id', db.Integer, db.ForeignKey('songs.id'), primary_key=True),
    db.Column('position', db.Integer, nullable=False, default=0),
    db.Column('added_at', db.DateTime, default=now_utc, nullable=False),
)


class Like(db.Model):
    __tablename__ = 'likes'

    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), primary_key=True)
    song_id = db.Column(db.Integer, db.ForeignKey('songs.id'), primary_key=True)
    created_at = db.Column(db.DateTime, default=now_utc, nullable=False)


class PlayHistory(db.Model):
    __tablename__ = 'play_history'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    song_id = db.Column(db.Integer, db.ForeignKey('songs.id'), nullable=False, index=True)
    played_at = db.Column(db.DateTime, default=now_utc, nullable=False, index=True)

    song = db.relationship('Song')
