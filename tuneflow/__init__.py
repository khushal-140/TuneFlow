"""TuneFlow — a self-hosted personal music streaming platform.

Flask app factory. Blueprints expose a JSON API under /api/*; the frontend is a
vanilla-JS single page app served from templates/index.html + static/.
"""
import os

from flask import Flask, jsonify, render_template, send_from_directory

from .extensions import db

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def create_app():
    app = Flask(
        __name__,
        static_folder=os.path.join(PROJECT_ROOT, 'static'),
        template_folder=os.path.join(PROJECT_ROOT, 'templates'),
    )

    app.config['SECRET_KEY'] = os.environ.get('TUNEFLOW_SECRET_KEY', 'tuneflow-dev-secret-change-me')
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['MAX_CONTENT_LENGTH'] = 200 * 1024 * 1024  # 200 MB uploads
    app.config['JSON_SORT_KEYS'] = False

    data_dir = os.environ.get('DATA_DIR', '').strip()
    if data_dir:
        # Persistent storage (e.g. a Render disk mounted at /var/data): keep the
        # database and media there instead of the ephemeral app directory.
        os.makedirs(data_dir, exist_ok=True)
        app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(data_dir, 'tuneflow.db')
        app.config['UPLOAD_DIR'] = os.path.join(data_dir, 'uploads')
        app.config['COVER_DIR'] = os.path.join(data_dir, 'covers')
        os.makedirs(app.config['UPLOAD_DIR'], exist_ok=True)
        os.makedirs(app.config['COVER_DIR'], exist_ok=True)
        # Keep /static/uploads and /static/covers URLs working by symlinking
        # them to the persistent locations (works on Linux hosts like Render).
        for name, target in (('uploads', app.config['UPLOAD_DIR']),
                             ('covers', app.config['COVER_DIR'])):
            static_target = os.path.join(app.static_folder, name)
            try:
                if os.path.islink(static_target):
                    os.remove(static_target)
                elif os.path.isdir(static_target) and not os.listdir(static_target):
                    os.rmdir(static_target)
                if not os.path.exists(static_target):
                    os.symlink(target, static_target)
            except OSError:
                pass  # non-fatal (e.g. Windows without symlink privilege)
    else:
        os.makedirs(app.instance_path, exist_ok=True)
        app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(app.instance_path, 'tuneflow.db')
        app.config['UPLOAD_DIR'] = os.path.join(app.static_folder, 'uploads')
        app.config['COVER_DIR'] = os.path.join(app.static_folder, 'covers')
        os.makedirs(app.config['UPLOAD_DIR'], exist_ok=True)
        os.makedirs(app.config['COVER_DIR'], exist_ok=True)

    db.init_app(app)

    from .auth import auth_bp
    from .library import library_bp
    from .uploads import uploads_bp
    from .playlists import playlists_bp
    from .ai import ai_bp
    from .converter import converter_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(library_bp)
    app.register_blueprint(uploads_bp)
    app.register_blueprint(playlists_bp)
    app.register_blueprint(ai_bp)
    app.register_blueprint(converter_bp)

    @app.get('/')
    def index():
        return render_template('index.html')

    @app.get('/favicon.ico')
    def favicon():
        return send_from_directory(app.static_folder, 'img/favicon.svg', mimetype='image/svg+xml')

    @app.get('/api/health')
    def health():
        from .converter import _cookie_file, _ffmpeg_binary
        return jsonify(ok=True, app='TuneFlow',
                       ffmpeg=bool(_ffmpeg_binary()),
                       yt_cookies=bool(_cookie_file()))

    @app.errorhandler(404)
    def not_found(_e):
        return jsonify(error='Not found.'), 404

    @app.errorhandler(405)
    def bad_method(_e):
        return jsonify(error='Method not allowed.'), 405

    @app.errorhandler(413)
    def too_large(_e):
        return jsonify(error='That file is too large — the limit is 200 MB.'), 413

    @app.errorhandler(500)
    def server_error(_e):
        return jsonify(error='Something went wrong on the server.'), 500

    with app.app_context():
        db.create_all()

    return app
