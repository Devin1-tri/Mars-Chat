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
    os.environ['_MARS_BUNDLED'] = '1'
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

os.chdir(BASE_DIR)

# Ensure data directories exist
os.makedirs('static/uploads', exist_ok=True)
os.makedirs('templates', exist_ok=True)

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
    uvicorn.run("app:app", host="0.0.0.0", port=8080, log_level="info")
