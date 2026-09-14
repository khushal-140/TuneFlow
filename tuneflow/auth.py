"""Authentication: register / login / logout / me — session based."""
import re

from flask import Blueprint, jsonify, request, session

from .extensions import db
from .helpers import current_user, login_required
from .models import User

auth_bp = Blueprint('auth', __name__)

USERNAME_RE = re.compile(r'^[A-Za-z0-9_.-]{3,24}$')
EMAIL_RE = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')


@auth_bp.post('/api/auth/register')
def register():
    data = request.get_json(silent=True) or {}
    username = (data.get('username') or '').strip()
    email = (data.get('email') or '').strip().lower()
    password = data.get('password') or ''

    if not USERNAME_RE.match(username):
        return jsonify(error='Username must be 3-24 characters (letters, numbers, _ . -).'), 400
    if not EMAIL_RE.match(email):
        return jsonify(error='Please enter a valid email address.'), 400
    if len(password) < 6:
        return jsonify(error='Password must be at least 6 characters.'), 400
    if User.query.filter(db.func.lower(User.username) == username.lower()).first():
        return jsonify(error='That username is taken.'), 409
    if User.query.filter(db.func.lower(User.email) == email).first():
        return jsonify(error='An account with that email already exists.'), 409

    user = User(username=username, email=email)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()

    session.clear()
    session['uid'] = user.id
    session.permanent = True
    return jsonify(user=user.to_dict())


@auth_bp.post('/api/auth/login')
def login():
    data = request.get_json(silent=True) or {}
    identifier = (data.get('identifier') or data.get('username') or '').strip()
    password = data.get('password') or ''

    if not identifier or not password:
        return jsonify(error='Enter your username/email and password.'), 400

    user = User.query.filter(
        (db.func.lower(User.username) == identifier.lower())
        | (db.func.lower(User.email) == identifier.lower())
    ).first()

    if user is None or not user.check_password(password):
        return jsonify(error='Wrong username or password.'), 401

    session.clear()
    session['uid'] = user.id
    session.permanent = True
    return jsonify(user=user.to_dict())


@auth_bp.post('/api/auth/logout')
def logout():
    session.clear()
    return jsonify(ok=True)


@auth_bp.get('/api/me')
def me():
    user = current_user()
    if user is None:
        return jsonify(error='Not signed in.'), 401
    return jsonify(user=user.to_dict())
