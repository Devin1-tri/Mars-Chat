"""
Mars Chat Launcher
Starts the server and opens a native window. No console shown.
"""
import os
import sys
import logging
import threading
import time

# Fix paths for PyInstaller bundle
if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
    sys.path.insert(0, sys._MEIPASS)
    os.chdir(sys._MEIPASS)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Log to file (no console window)
log_path = os.path.join(BASE_DIR, 'marschat.log')
logging.basicConfig(
    filename=log_path,
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
)
logger = logging.getLogger('marschat')

# Ensure data directories exist
os.makedirs(os.path.join(BASE_DIR, 'static', 'uploads'), exist_ok=True)

def wait_for_server(host='localhost', port=8080, timeout=30):
    """Wait until the server is ready."""
    import urllib.request
    import urllib.error
    start = time.time()
    while time.time() - start < timeout:
        try:
            urllib.request.urlopen(f'http://{host}:{port}/login', timeout=2)
            return True
        except (urllib.error.URLError, ConnectionError, OSError):
            time.sleep(0.3)
    return False

if __name__ == '__main__':
    logger.info("Mars Chat starting...")

    # Start uvicorn in background thread
    def run_server():
        try:
            import uvicorn
            from app import app
            uvicorn.run(app, host="0.0.0.0", port=8080, log_level="warning")
        except Exception as e:
            logger.exception("Server crashed")

    server_thread = threading.Thread(target=run_server, daemon=True)
    server_thread.start()

    # Wait for server to be ready
    if not wait_for_server():
        logger.error("Server failed to start within 30s")
        sys.exit(1)

    logger.info("Server ready, opening window...")

    # Open native window
    try:
        import webview
        window = webview.create_window(
            'Mars Chat',
            'http://localhost:8080/chat',
            width=1200,
            height=800,
            min_size=(800, 600),
        )
        webview.start()
    except Exception as e:
        logger.exception("Window failed")

    logger.info("Window closed, exiting.")
    os._exit(0)
