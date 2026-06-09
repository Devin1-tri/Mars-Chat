"""
Mars Chat — Local Office Chat Application v1.0
FastAPI + WebSocket + SQLite + Jinja2 + TailwindCSS
Features: DM, Group Chat, File/Image Upload, Online Status
"""

import os
import sqlite3
import hashlib
import secrets
import json
import uuid
import inspect
from datetime import datetime
from contextlib import contextmanager
from functools import wraps
from typing import Dict, Set, Optional

from fastapi import FastAPI, Request, Form, Query, Cookie, Response, WebSocket, WebSocketDisconnect, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import aiofiles

# ── Config ──────────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "mars_chat.db")
UPLOAD_DIR = os.path.join(BASE_DIR, "static", "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB

app = FastAPI(title="Mars Chat")
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

# ── Database ────────────────────────────────────────────────────────────
@contextmanager
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()

def init_db():
    with get_db() as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            display_name TEXT NOT NULL,
            avatar_color TEXT DEFAULT '#3B82F6',
            avatar_url TEXT DEFAULT '',
            bio TEXT DEFAULT '',
            is_online INTEGER DEFAULT 0,
            last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS conversations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            type TEXT NOT NULL CHECK(type IN ('dm', 'group')),
            name TEXT DEFAULT '',
            avatar_color TEXT DEFAULT '#6366F1',
            created_by INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE SET NULL
        );

        CREATE TABLE IF NOT EXISTS conversation_members (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            role TEXT DEFAULT 'member' CHECK(role IN ('admin', 'member')),
            joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            UNIQUE(conversation_id, user_id)
        );

        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            content TEXT DEFAULT '',
            msg_type TEXT DEFAULT 'text' CHECK(msg_type IN ('text', 'image', 'file')),
            file_name TEXT DEFAULT '',
            file_path TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS read_receipts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            message_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            read_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (message_id) REFERENCES messages(id) ON DELETE CASCADE,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            UNIQUE(message_id, user_id)
        );
        """)

init_db()

# ── Migration ──────────────────────────────────────────────────────────
def migrate_db():
    with get_db() as db:
        cols = [row[1] for row in db.execute("PRAGMA table_info(users)").fetchall()]
        if 'avatar_url' not in cols:
            db.execute("ALTER TABLE users ADD COLUMN avatar_url TEXT DEFAULT ''")
        if 'bio' not in cols:
            db.execute("ALTER TABLE users ADD COLUMN bio TEXT DEFAULT ''")
migrate_db()

# ── Helpers ─────────────────────────────────────────────────────────────
AVATAR_COLORS = ['#EF4444', '#F97316', '#EAB308', '#22C55E', '#3B82F6', '#8B5CF6', '#EC4899', '#06B6D4']

def hash_password(pw: str) -> str:
    return hashlib.sha256(pw.encode()).hexdigest()

def get_current_user(request: Request):
    token = request.cookies.get("session_token")
    if not token:
        return None
    with get_db() as db:
        user = db.execute("SELECT * FROM users WHERE username = ?", (token,)).fetchone()
    return user


def require_auth(f):
    @wraps(f)
    async def decorated(request: Request, *args, **kwargs):
        user = get_current_user(request)
        if not user:
            return RedirectResponse("/login", status_code=303)
        request.state.user = user
        if inspect.iscoroutinefunction(f):
            return await f(request, *args, **kwargs)
        else:
            return f(request, *args, **kwargs)
    return decorated

def format_time(val):
    if val is None: return ""
    if isinstance(val, str):
        try:
            val = datetime.fromisoformat(val.replace("Z", "+00:00"))
        except: return val
    if isinstance(val, datetime):
        now = datetime.now()
        if val.date() == now.date():
            return val.strftime("%H:%M")
        return val.strftime("%d/%m %H:%M")
    return str(val)

templates.env.filters["format_time"] = format_time

# ── WebSocket Manager ───────────────────────────────────────────────────
class ConnectionManager:
    def __init__(self):
        self.active: Dict[int, WebSocket] = {}  # user_id -> websocket
        self.user_conversations: Dict[int, Set[int]] = {}  # user_id -> set of conv_ids

    async def connect(self, user_id: int, websocket: WebSocket):
        await websocket.accept()
        self.active[user_id] = websocket
        # Update online status
        with get_db() as db:
            db.execute("UPDATE users SET is_online=1, last_seen=CURRENT_TIMESTAMP WHERE id=?", (user_id,))
        # Notify others
        await self.broadcast_user_status(user_id, True)

    async def disconnect(self, user_id: int):
        if user_id in self.active:
            del self.active[user_id]
        with get_db() as db:
            db.execute("UPDATE users SET is_online=0, last_seen=CURRENT_TIMESTAMP WHERE id=?", (user_id,))
        await self.broadcast_user_status(user_id, False)

    async def broadcast_user_status(self, user_id: int, online: bool):
        msg = json.dumps({"type": "status", "user_id": user_id, "online": online})
        for uid, ws in list(self.active.items()):
            if uid != user_id:
                try:
                    await ws.send_text(msg)
                except:
                    pass

    async def send_to_conversation(self, conv_id: int, message: dict, exclude_user: int = None):
        msg = json.dumps(message)
        with get_db() as db:
            members = db.execute("SELECT user_id FROM conversation_members WHERE conversation_id=?", (conv_id,)).fetchall()
        dead = []
        for m in members:
            uid = m["user_id"]
            if uid != exclude_user and uid in self.active:
                try:
                    await self.active[uid].send_text(msg)
                except Exception:
                    dead.append(uid)
        for uid in dead:
            if uid in self.active:
                del self.active[uid]

    async def send_to_user(self, user_id: int, message: dict):
        if user_id in self.active:
            try:
                await self.active[user_id].send_text(json.dumps(message))
            except:
                pass

manager = ConnectionManager()

# ═══════════════════════════════════════════════════════════════════════
# ROUTES: AUTH
# ═══════════════════════════════════════════════════════════════════════
@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    user = get_current_user(request)
    if user:
        return RedirectResponse("/chat", status_code=303)
    return RedirectResponse("/login", status_code=303)

@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request, error: str = ""):
    return templates.TemplateResponse(request, "login.html", {"error": error})

@app.post("/login")
def login(request: Request, response: Response, username: str = Form(...), password: str = Form(...)):
    pw_hash = hash_password(password)
    with get_db() as db:
        user = db.execute("SELECT * FROM users WHERE username=? AND password_hash=?", (username, pw_hash)).fetchone()
    if not user:
        return templates.TemplateResponse(request, "login.html", {"error": "Username atau password salah!"})
    response = RedirectResponse("/chat", status_code=303)
    response.set_cookie("session_token", user["username"], max_age=86400*7)
    return response

@app.get("/register", response_class=HTMLResponse)
def register_page(request: Request, error: str = ""):
    return templates.TemplateResponse(request, "register.html", {"error": error})

@app.post("/register")
def register(request: Request, username: str = Form(...), password: str = Form(...),
             display_name: str = Form(...)):
    import random
    color = random.choice(AVATAR_COLORS)
    with get_db() as db:
        existing = db.execute("SELECT id FROM users WHERE username=?", (username,)).fetchone()
        if existing:
            return templates.TemplateResponse(request, "register.html", {"error": "Username sudah dipakai!"})
        db.execute("INSERT INTO users (username, password_hash, display_name, avatar_color) VALUES (?, ?, ?, ?)",
                   (username, hash_password(password), display_name, color))
    response = RedirectResponse("/chat", status_code=303)
    response.set_cookie("session_token", username, max_age=86400*7)
    return response

@app.get("/logout")
def logout():
    response = RedirectResponse("/login", status_code=303)
    response.delete_cookie("session_token")
    return response

# ═══════════════════════════════════════════════════════════════════════
# ROUTES: CHAT PAGE
# ═══════════════════════════════════════════════════════════════════════
@app.get("/chat", response_class=HTMLResponse)
@require_auth
def chat_page(request: Request):
    user = request.state.user
    with get_db() as db:
        # Get conversations
        conversations = db.execute("""
            SELECT c.*, cm.role,
                (SELECT content FROM messages WHERE conversation_id=c.id ORDER BY created_at DESC LIMIT 1) as last_message,
                (SELECT created_at FROM messages WHERE conversation_id=c.id ORDER BY created_at DESC LIMIT 1) as last_time,
                (SELECT COUNT(*) FROM messages m
                 WHERE m.conversation_id=c.id AND m.user_id != ?
                 AND m.id NOT IN (SELECT message_id FROM read_receipts WHERE user_id=?)) as unread
            FROM conversations c
            JOIN conversation_members cm ON c.id = cm.conversation_id AND cm.user_id = ?
            ORDER BY last_time DESC NULLS LAST, c.created_at DESC
        """, (user["id"], user["id"], user["id"])).fetchall()

        # Get all users for new chat
        all_users = db.execute("SELECT * FROM users WHERE id != ? ORDER BY display_name", (user["id"],)).fetchall()

    return templates.TemplateResponse(request, "chat.html", {
        "request": request, "user": user, "conversations": conversations, "all_users": all_users
    })

# ═══════════════════════════════════════════════════════════════════════
# ROUTES: API
# ═══════════════════════════════════════════════════════════════════════
@app.get("/api/conversations")
@require_auth
def api_conversations(request: Request):
    user = request.state.user
    with get_db() as db:
        convs = db.execute("""
            SELECT c.*,
                (SELECT content FROM messages WHERE conversation_id=c.id ORDER BY created_at DESC LIMIT 1) as last_message,
                (SELECT created_at FROM messages WHERE conversation_id=c.id ORDER BY created_at DESC LIMIT 1) as last_time,
                (SELECT COUNT(*) FROM messages m
                 WHERE m.conversation_id=c.id AND m.user_id != ?
                 AND m.id NOT IN (SELECT message_id FROM read_receipts WHERE user_id=?)) as unread
            FROM conversations c
            JOIN conversation_members cm ON c.id = cm.conversation_id AND cm.user_id = ?
            ORDER BY last_time DESC NULLS LAST, c.created_at DESC
        """, (user["id"], user["id"], user["id"])).fetchall()

        result = []
        for c in convs:
            conv = dict(c)
            # Get display info
            if c["type"] == "dm":
                other = db.execute("""
                    SELECT u.id, u.display_name, u.avatar_color, u.avatar_url, u.is_online
                    FROM users u JOIN conversation_members cm ON u.id = cm.user_id
                    WHERE cm.conversation_id = ? AND u.id != ?
                """, (c["id"], user["id"])).fetchone()
                if other:
                    conv["display_name"] = other["display_name"]
                    conv["avatar_color"] = other["avatar_color"]
                    conv["avatar_url"] = other["avatar_url"]
                    conv["is_online"] = other["is_online"]
                    conv["other_id"] = other["id"]
                else:
                    conv["display_name"] = "Unknown"
                    conv["avatar_color"] = "#6B7280"
                    conv["is_online"] = 0
            else:
                members = db.execute("""
                    SELECT u.id, u.display_name FROM users u
                    JOIN conversation_members cm ON u.id = cm.user_id
                    WHERE cm.conversation_id = ?
                """, (c["id"],)).fetchall()
                conv["member_count"] = len(members)
                conv["member_names"] = ", ".join([m["display_name"] for m in members[:5]])
            result.append(conv)
    return JSONResponse(result)

@app.get("/api/messages/{conv_id}")
@require_auth
def api_messages(request: Request, conv_id: int, before: int = 0):
    user = request.state.user
    with get_db() as db:
        # Verify membership
        member = db.execute("SELECT * FROM conversation_members WHERE conversation_id=? AND user_id=?",
                           (conv_id, user["id"])).fetchone()
        if not member:
            return JSONResponse({"error": "Not a member"}, status_code=403)

        if before:
            msgs = db.execute("""
                SELECT m.*, u.display_name, u.avatar_color
                FROM messages m JOIN users u ON m.user_id = u.id
                WHERE m.conversation_id=? AND m.id < ?
                ORDER BY m.created_at DESC LIMIT 50
            """, (conv_id, before)).fetchall()
        else:
            msgs = db.execute("""
                SELECT m.*, u.display_name, u.avatar_color
                FROM messages m JOIN users u ON m.user_id = u.id
                WHERE m.conversation_id=?
                ORDER BY m.created_at DESC LIMIT 50
            """, (conv_id,)).fetchall()

        # Mark as read
        for m in msgs:
            if m["user_id"] != user["id"]:
                db.execute("INSERT OR IGNORE INTO read_receipts (message_id, user_id) VALUES (?, ?)",
                          (m["id"], user["id"]))

        # Get conversation info
        conv = db.execute("SELECT * FROM conversations WHERE id=?", (conv_id,)).fetchone()
        conv_info = dict(conv)
        if conv["type"] == "group":
            members = db.execute("""
                SELECT u.id, u.display_name, u.avatar_color, u.is_online, cm.role
                FROM users u JOIN conversation_members cm ON u.id = cm.user_id
                WHERE cm.conversation_id = ?
            """, (conv_id,)).fetchall()
            conv_info["members"] = [dict(m) for m in members]

    return JSONResponse({
        "messages": [dict(m) for m in reversed(msgs)],
        "conversation": conv_info
    })

@app.post("/api/conversations/dm")
@require_auth
def create_dm(request: Request, other_user_id: int = Form(...)):
    user = request.state.user
    with get_db() as db:
        # Check if DM already exists
        existing = db.execute("""
            SELECT c.id FROM conversations c
            JOIN conversation_members cm1 ON c.id = cm1.conversation_id AND cm1.user_id = ?
            JOIN conversation_members cm2 ON c.id = cm2.conversation_id AND cm2.user_id = ?
            WHERE c.type = 'dm'
        """, (user["id"], other_user_id)).fetchone()

        if existing:
            return JSONResponse({"conversation_id": existing["id"]})

        # Create new DM
        db.execute("INSERT INTO conversations (type, created_by) VALUES ('dm', ?)", (user["id"],))
        conv_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]
        db.execute("INSERT INTO conversation_members (conversation_id, user_id) VALUES (?, ?)", (conv_id, user["id"]))
        db.execute("INSERT INTO conversation_members (conversation_id, user_id) VALUES (?, ?)", (conv_id, other_user_id))

    return JSONResponse({"conversation_id": conv_id})

@app.post("/api/conversations/group")
@require_auth
def create_group(request: Request, name: str = Form(...), member_ids: str = Form(...)):
    user = request.state.user
    import random
    color = random.choice(AVATAR_COLORS)
    ids = [int(x) for x in member_ids.split(",") if x.strip()]

    with get_db() as db:
        db.execute("INSERT INTO conversations (type, name, avatar_color, created_by) VALUES ('group', ?, ?, ?)",
                   (name, color, user["id"]))
        conv_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]
        db.execute("INSERT INTO conversation_members (conversation_id, user_id, role) VALUES (?, ?, 'admin')",
                   (conv_id, user["id"]))
        for uid in ids:
            db.execute("INSERT OR IGNORE INTO conversation_members (conversation_id, user_id) VALUES (?, ?)",
                       (conv_id, uid))

    return JSONResponse({"conversation_id": conv_id})

@app.post("/api/upload/{conv_id}")
@require_auth
async def upload_file(request: Request, conv_id: int, file: UploadFile = File(...)):
    user = request.state.user

    # Verify membership
    with get_db() as db:
        member = db.execute("SELECT * FROM conversation_members WHERE conversation_id=? AND user_id=?",
                           (conv_id, user["id"])).fetchone()
        if not member:
            return JSONResponse({"error": "Not a member"}, status_code=403)

    # Save file
    ext = os.path.splitext(file.filename)[1] if file.filename else ""
    filename = f"{uuid.uuid4().hex}{ext}"
    filepath = os.path.join(UPLOAD_DIR, filename)

    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        return JSONResponse({"error": "File terlalu besar (max 10MB)"}, status_code=400)

    async with aiofiles.open(filepath, 'wb') as f:
        await f.write(content)

    # Determine msg_type
    img_exts = {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp'}
    msg_type = "image" if ext.lower() in img_exts else "file"

    # Save message
    with get_db() as db:
        db.execute("""
            INSERT INTO messages (conversation_id, user_id, content, msg_type, file_name, file_path)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (conv_id, user["id"], file.filename, msg_type, file.filename, f"/static/uploads/{filename}"))
        msg_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]
        msg = db.execute("SELECT m.*, u.display_name, u.avatar_color FROM messages m JOIN users u ON m.user_id=u.id WHERE m.id=?", (msg_id,)).fetchone()

    msg_dict = dict(msg)
    await manager.send_to_conversation(conv_id, {"type": "new_message", "message": msg_dict}, exclude_user=user["id"])
    return JSONResponse(msg_dict)

# ═══════════════════════════════════════════════════════════════════════
# WEBSOCKET
# ═══════════════════════════════════════════════════════════════════════
@app.websocket("/ws/{token}")
async def websocket_endpoint(websocket: WebSocket, token: str):
    # Authenticate
    with get_db() as db:
        user = db.execute("SELECT * FROM users WHERE username=?", (token,)).fetchone()
    if not user:
        await websocket.close(code=4001)
        return

    user_id = user["id"]
    await manager.connect(user_id, websocket)

    try:
        while True:
            data = await websocket.receive_text()
            payload = json.loads(data)

            if payload["type"] == "message":
                conv_id = payload["conversation_id"]
                content = payload.get("content", "")
                msg_type = payload.get("msg_type", "text")

                # Verify membership
                with get_db() as db:
                    member = db.execute("SELECT * FROM conversation_members WHERE conversation_id=? AND user_id=?",
                                       (conv_id, user_id)).fetchone()
                    if not member:
                        continue

                    db.execute("""
                        INSERT INTO messages (conversation_id, user_id, content, msg_type)
                        VALUES (?, ?, ?, ?)
                    """, (conv_id, user_id, content, msg_type))
                    msg_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]
                    msg = db.execute("""
                        SELECT m.*, u.display_name, u.avatar_color
                        FROM messages m JOIN users u ON m.user_id=u.id WHERE m.id=?
                    """, (msg_id,)).fetchone()

                msg_dict = dict(msg)
                # Send to all members
                await manager.send_to_conversation(conv_id, {"type": "new_message", "message": msg_dict})

            elif payload["type"] == "typing":
                await manager.send_to_conversation(
                    payload["conversation_id"],
                    {"type": "typing", "user_id": user_id, "display_name": user["display_name"]},
                    exclude_user=user_id
                )

            elif payload["type"] == "read":
                conv_id = payload["conversation_id"]
                with get_db() as db:
                    db.execute("""
                        INSERT OR IGNORE INTO read_receipts (message_id, user_id)
                        SELECT m.id, ? FROM messages m
                        WHERE m.conversation_id=? AND m.user_id != ?
                        AND m.id NOT IN (SELECT message_id FROM read_receipts WHERE user_id=?)
                    """, (user_id, conv_id, user_id, user_id))

    except WebSocketDisconnect:
        await manager.disconnect(user_id)
    except Exception:
        await manager.disconnect(user_id)

# ═══════════════════════════════════════════════════════════════════════
# ROUTES: API - USERS & PROFILE
# ═══════════════════════════════════════════════════════════════════════
@app.get("/api/users/online")
@require_auth
def api_users_online(request: Request):
    user = request.state.user
    with get_db() as db:
        users = db.execute("""
            SELECT id, username, display_name, avatar_color, avatar_url, bio, is_online, last_seen
            FROM users WHERE id != ? ORDER BY is_online DESC, display_name ASC
        """, (user["id"],)).fetchall()
    return JSONResponse([dict(u) for u in users])

@app.get("/api/profile/{user_id}")
@require_auth
def api_profile(request: Request, user_id: int):
    with get_db() as db:
        u = db.execute("SELECT id, username, display_name, avatar_color, avatar_url, bio, is_online, last_seen, created_at FROM users WHERE id=?", (user_id,)).fetchone()
    if not u:
        return JSONResponse({"error": "User not found"}, status_code=404)
    return JSONResponse(dict(u))

@app.post("/api/profile/update")
@require_auth
async def api_profile_update(request: Request):
    user = request.state.user
    form = await request.form()
    bio = form.get("bio", "")
    avatar_url = form.get("avatar_url", "")

    # Handle file upload
    avatar_file = form.get("avatar_file")
    if avatar_file and hasattr(avatar_file, 'filename') and avatar_file.filename:
        ext = os.path.splitext(avatar_file.filename)[1].lower()
        if ext in {'.jpg', '.jpeg', '.png', '.gif', '.webp'}:
            filename = f"avatar_{user['id']}_{uuid.uuid4().hex[:8]}{ext}"
            filepath = os.path.join(UPLOAD_DIR, filename)
            content = await avatar_file.read()
            if len(content) <= 5 * 1024 * 1024:  # 5MB max for avatars
                async with aiofiles.open(filepath, 'wb') as f:
                    await f.write(content)
                avatar_url = f"/static/uploads/{filename}"

    with get_db() as db:
        db.execute("UPDATE users SET bio=?, avatar_url=? WHERE id=?", (bio, avatar_url, user["id"]))

    return JSONResponse({"ok": True})

# ═══════════════════════════════════════════════════════════════════════
# ROUTES: GROUP MANAGEMENT
# ═══════════════════════════════════════════════════════════════════════
@app.post("/api/group/{conv_id}/add")
@require_auth
def add_group_member(request: Request, conv_id: int, user_id: int = Form(...)):
    user = request.state.user
    with get_db() as db:
        admin = db.execute("SELECT * FROM conversation_members WHERE conversation_id=? AND user_id=? AND role='admin'",
                          (conv_id, user["id"])).fetchone()
        if not admin:
            return JSONResponse({"error": "Only admin can add members"}, status_code=403)
        db.execute("INSERT OR IGNORE INTO conversation_members (conversation_id, user_id) VALUES (?, ?)",
                   (conv_id, user_id))
    return JSONResponse({"ok": True})

@app.post("/api/group/{conv_id}/leave")
@require_auth
def leave_group(request: Request, conv_id: int):
    user = request.state.user
    with get_db() as db:
        db.execute("DELETE FROM conversation_members WHERE conversation_id=? AND user_id=?",
                   (conv_id, user["id"]))
    return JSONResponse({"ok": True})

@app.post("/api/conversations/{conv_id}/clear")
@require_auth
def clear_conversation(request: Request, conv_id: int):
    user = request.state.user
    with get_db() as db:
        member = db.execute("SELECT * FROM conversation_members WHERE conversation_id=? AND user_id=?",
                           (conv_id, user["id"])).fetchone()
        if not member:
            return JSONResponse({"error": "Not a member"}, status_code=403)
        db.execute("DELETE FROM messages WHERE conversation_id=?", (conv_id,))
        db.execute("DELETE FROM conversation_members WHERE conversation_id=?", (conv_id,))
        db.execute("DELETE FROM conversations WHERE id=?", (conv_id,))
    return JSONResponse({"ok": True})

# ═══════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
