"""
Mars Chat Launcher
Starts the server and opens the browser automatically.
"""
import os
import sys
import webbrowser
import threading
import time

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

def open_browser():
    time.sleep(2)
    webbrowser.open('http://localhost:8080/chat')

if __name__ == '__main__':
    print("=" * 50)
    print("  🚀 Mars Chat Server")
    print("  Running on http://localhost:8080")
    print("  Press Ctrl+C to stop")
    print("=" * 50)

    # Open browser after short delay
    threading.Thread(target=open_browser, daemon=True).start()

    import uvicorn
    from app import app
    uvicorn.run(app, host="0.0.0.0", port=8080, log_level="info")
