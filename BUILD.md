# 🚀 Mars Chat — Build & Deploy Guide

## Build EXE

```bash
# Run the build script
build.bat
```

Output: `dist/MarsChat.exe`

## Auto-Run on Windows Startup

```bash
# After building, run this as Administrator
setup_autorun.bat
```

This creates a hidden launcher in the Windows Startup folder.
To remove: delete `%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\MarsChat.lnk`

## Manual Run (Development)

```bash
pip install -r requirements.txt
python app.py
```

Open http://localhost:8080

## Admin Dashboard

First registered user is automatically admin.
Access: http://localhost:8080/admin

## Features

- 💬 Real-time chat (WebSocket)
- 👥 DM & Group chat
- 📎 File/Image upload
- 😀 Emoji picker
- 🌗 Dark/Light mode
- 🛡️ Admin dashboard
- 📦 Standalone .exe
- 🔄 Auto-run on startup
