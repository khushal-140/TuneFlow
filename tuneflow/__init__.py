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
    os.makedirs(app.instance_path, exist_ok=True)
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(app.instance_path, 'tuneflow.db')
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['MAX_CONTENT_LENGTH'] = 200 * 1024 * 1024  # 200 MB uploads
    app.config['JSON_SORT_KEYS'] = False

    # Media directories
    app.config['UPLOAD_DIR'] = os.path.join(app.static_folder, 'uploads')
    app.config['COVER_DIR'] = os.path.join(app.static_folder, 'covers')
    for d in (app.config['UPLOAD_DIR'], app.config['COVER_DIR']):
        os.makedirs(d, exist_ok=True)

    db.init_app(app)

    from .auth import auth_bp
    from .library import library_bp
    from .uploads import uploads_bp
    from .playlists import playlists_bp
    from .ai import ai_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(library_bp)
    app.register_blueprint(uploads_bp)
    app.register_blueprint(playlists_bp)
    app.register_blueprint(ai_bp)

    @app.get('/')
    def index():
        return render_template('index.html')

    @app.get('/favicon.ico')
    def favicon():
        return send_from_directory(app.static_folder, 'img/favicon.svg', mimetype='image/svg+xml')

    @app.get('/api/health')
    def health():
        return jsonify(ok=True, app='TuneFlow')

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
