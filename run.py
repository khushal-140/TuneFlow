"""Run TuneFlow locally: python run.py"""
import os

from tuneflow import create_app

app = create_app()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print(f'TuneFlow running on http://127.0.0.1:{port}')
    app.run(host='127.0.0.1', port=port, debug=True)
