"""Small shared helpers: current user, auth guard, media path resolution."""
import os
from functools import wraps

from flask import jsonify, session

from .extensions import db
from .models import User
from .timeutil import iso, now_utc  # noqa: F401  (re-exported for convenience)


def current_user():
    uid = session.get('uid')
    if uid is None:
        return None
    return db.session.get(User, uid)


def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        user = current_user()
        if user is None:
            return jsonify(error='You need to be signed in.'), 401
        return fn(user, *args, **kwargs)
    return wrapper


def bad_request(msg):
    return jsonify(error=msg), 400


def resolve_media_path(kind, rel):
    """Resolve a stored media reference ('uploads/...' or 'covers/...') to a real
    path inside the configured media directory (which may be a persistent disk
    symlinked into static/). Returns None when the reference is unsafe."""
    key = 'UPLOAD_DIR' if kind == 'uploads' else 'COVER_DIR'
    try:
        from flask import current_app
        base = os.path.realpath(current_app.config[key])
    except (RuntimeError, KeyError):
        return None
    name = (rel or '').split(kind + '/', 1)[-1].lstrip('/').replace('\\', '/')
    if not name or '/' in name or '..' in name:
        return None
    path = os.path.realpath(os.path.join(base, name))
    return path if path.startswith(base + os.sep) else None
