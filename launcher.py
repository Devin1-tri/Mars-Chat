"""
Mars Chat Launcher
Starts the server and opens a native desktop window automatically.
"""
import os
import sys
import threading
import time
import urllib.request
import urllib.error

# Fix paths for PyInstaller bundle
if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
    # Add bundle dir to path so app module can be found
    sys.path.insert(0, sys._MEIPASS)
    os.chdir(sys._MEIPASS)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Ensure data directories exist in the exe's directory
os.makedirs(os.path.join(BASE_DIR, 'static', 'uploads'), exist_ok=True)

SERVER_URL = 'http://localhost:8080'


def start_server():
    """Run uvicorn server (called in a daemon thread)."""
    import uvicorn
    from app import app
    uvicorn.run(app, host='0.0.0.0', port=8080, log_level='info')


def wait_for_server(url, timeout=30):
    """Poll the server until it responds or timeout is reached."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            urllib.request.urlopen(url, timeout=1)
            return True
        except (urllib.error.URLError, ConnectionError, OSError):
            time.sleep(0.3)
    return False


if __name__ == '__main__':
    print('=' * 50)
    print('  Mars Chat Server')
    print(f'  Running on {SERVER_URL}')
    print('  Press Ctrl+C to stop')
    print('=' * 50)

    # Start uvicorn in a daemon thread
    server_thread = threading.Thread(target=start_server, daemon=True)
    server_thread.start()

    # Wait for the server to become ready
    if not wait_for_server(SERVER_URL):
        print('ERROR: Server failed to start within 30 seconds.')
        sys.exit(1)

    # Open native window
    import webview
    webview.create_window(
        'Mars Chat',
        url=f'{SERVER_URL}/chat',
        width=1200,
        height=800,
    )
    webview.start()

    # Window was closed – exit the process
    sys.exit(0)
