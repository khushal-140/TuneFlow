"""Small shared helpers: current user, auth guard, JSON errors."""
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
