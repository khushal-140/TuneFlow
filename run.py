"""Run TuneFlow locally: python run.py"""
import os

from tuneflow import create_app

app = create_app()

if __name__ == '__main__':
    # Render (and most platforms) require binding 0.0.0.0 — they set PORT for us.
    # Binding 127.0.0.1 only listens inside the container, so Render reports
    # "No open ports detected" and the service never comes online.
    port = int(os.environ.get('PORT', 5000))
    host = os.environ.get('HOST', '0.0.0.0')
    # Debug mode (auto-reload + Werkzeug debugger) only when explicitly enabled —
    # never on a public server: the interactive debugger is a code-execution risk.
    debug = os.environ.get('FLASK_DEBUG', '') == '1'
    print(f'TuneFlow running on http://{host}:{port}')
    app.run(host=host, port=port, debug=debug)
