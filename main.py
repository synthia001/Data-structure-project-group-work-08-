from fastapi import (
    FastAPI,
    WebSocket,
    WebSocketDisconnect,
    UploadFile,
    File,
    Form,
    HTTPException,
    Depends,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import json
import sqlite3
import os
import shutil
import hashlib
import secrets
from datetime import datetime
from pydantic import BaseModel

# ── App ──
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Static files ──
os.makedirs("static", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")

security = HTTPBearer()

# ── Database ──
DB = "mku.db"

def db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_model=WAL")
    return conn

def init_db():
    c = db()
    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            first_name TEXT,
            last_name TEXT,
            username TEXT UNIQUE NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            token TEXT,
            avatar_url TEXT,
            posts_count INTEGER DEFAULT 0,
            followers_count INTEGER DEFAULT 0,
            following_count INTEGER DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now'))
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            content TEXT NOT NULL,
            image_url TEXT,
            likes_count INTEGER DEFAULT 0,
            comments_count INTEGER DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS likes (
            user_id INTEGER,
            post_id INTEGER,
            PRIMARY KEY (user_id, post_id)
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS comments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            post_id INTEGER,
            content TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS follows (
            follower_id INTEGER,
            following_id INTEGER,
            PRIMARY KEY (follower_id, following_id)
        )
    """)
    c.commit()
    c.close()

init_db()

# ── Helpers ──
def hash_pw(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

def make_token() -> str:
    return secrets.token_hex(32)

def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    token = credentials.credentials
    c = db()
    user = c.execute("SELECT * FROM users WHERE token=?", (token,)).fetchone()
    c.close()
    if not user:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return dict(user)

# ── Models ──
class RegisterModel(BaseModel):
    first_name: str
    last_name: str
    username: str
    email: str
    password: str

class LoginModel(BaseModel):
    username: str
    password: str

class PostModel(BaseModel):
    content: str

class CommentModel(BaseModel):
    content: str

# ════════════════════════════
#  AUTH
# ════════════════════════════

@app.post("/register")
async def register(data: RegisterModel):
    c = db()
    # Check if username or email already exists
    existing = c.execute(
        "SELECT id FROM users WHERE username=? OR email=?",
        (data.username, data.email)
    ).fetchone()
    if existing:
        c.close()
        raise HTTPException(status_code=400, detail="Username or email already taken.")

    hashed = hash_pw(data.password)
    c.execute(
        "INSERT INTO users (first_name, last_name, username, email, password) VALUES (?,?,?,?,?)",
        (data.first_name, data.last_name, data.username, data.email, hashed)
    )
    c.commit()
    c.close()
    return {"ok": True, "message": "Account created successfully!"}


@app.post("/auth/login")
async def login(data: LoginModel):
    c = db()
    user = c.execute(
        "SELECT * FROM users WHERE username=? AND password=?",
        (data.username, hash_pw(data.password))
    ).fetchone()
    if not user:
        c.close()
        raise HTTPException(status_code=401, detail="Invalid username or password.")
    token = make_token()
    c.execute("UPDATE users SET token=? WHERE id=?", (token, user["id"]))
    c.commit()
    c.close()
    return {
        "ok": True,
        "access_token": token,
        "username": user["username"],
        "id": user["id"],
    }


# ════════════════════════════
#  USERS
# ════════════════════════════

@app.get("/users/me")
async def get_me(current_user: dict = Depends(get_current_user)):
    return {
        "id": current_user["id"],
        "username": current_user["username"],
        "full_name": f"{current_user['first_name']} {current_user['last_name']}",
        "email": current_user["email"],
        "avatar_url": current_user["avatar_url"],
        "posts_count": current_user["posts_count"],
        "followers_count": current_user["followers_count"],
        "following_count": current_user["following_count"],
    }


@app.get("/users/suggestions")
async def suggestions(current_user: dict = Depends(get_current_user)):
    c = db()
    users = c.execute(
        "SELECT id, username, first_name, last_name FROM users WHERE id != ? LIMIT 6",
        (current_user["id"],)
    ).fetchall()
    c.close()
    return [
        {
            "id": u["id"],
            "username": u["username"],
            "full_name": f"{u['first_name']} {u['last_name']}",
        }
        for u in users
    ]


@app.post("/users/{user_id}/follow")
async def follow(user_id: int, current_user: dict = Depends(get_current_user)):
    c = db()
    c.execute(
        "INSERT OR IGNORE INTO follows (follower_id, following_id) VALUES (?,?)",
        (current_user["id"], user_id)
    )
    c.execute("UPDATE users SET followers_count = followers_count+1 WHERE id=?", (user_id,))
    c.execute("UPDATE users SET following_count = following_count+1 WHERE id=?", (current_user["id"],))
    c.commit()
    c.close()
    return {"ok": True}


@app.delete("/users/{user_id}/follow")
async def unfollow(user_id: int, current_user: dict = Depends(get_current_user)):
    c = db()
    c.execute(
        "DELETE FROM follows WHERE follower_id=? AND following_id=?",
        (current_user["id"], user_id)
    )
    c.execute("UPDATE users SET followers_count = MAX(0, followers_count-1) WHERE id=?", (user_id,))
    c.execute("UPDATE users SET following_count = MAX(0, following_count-1) WHERE id=?", (current_user["id"],))
    c.commit()
    c.close()
    return {"ok": True}


# ════════════════════════════
#  POSTS
# ════════════════════════════

@app.get("/posts")
async def get_posts(current_user: dict = Depends(get_current_user)):
    c = db()
    posts = c.execute("""
        SELECT p.*, u.username, u.first_name, u.last_name, u.avatar_url
        FROM posts p
        JOIN users u ON p.user_id = u.id
        ORDER BY p.created_at DESC
        LIMIT 50
    """).fetchall()

    result = []
    for p in posts:
        liked = c.execute(
            "SELECT 1 FROM likes WHERE user_id=? AND post_id=?",
            (current_user["id"], p["id"])
        ).fetchone()
        result.append({
            "id": p["id"],
            "content": p["content"],
            "image_url": p["image_url"],
            "likes_count": p["likes_count"],
            "comments_count": p["comments_count"],
            "created_at": p["created_at"],
            "liked_by_me": liked is not None,
            "author": {
                "id": p["user_id"],
                "username": p["username"],
                "full_name": f"{p['first_name']} {p['last_name']}",
                "avatar_url": p["avatar_url"],
            }
        })
    c.close()
    return result


@app.post("/posts")
async def create_post(data: PostModel, current_user: dict = Depends(get_current_user)):
    c = db()
    cursor = c.execute(
        "INSERT INTO posts (user_id, content) VALUES (?,?)",
        (current_user["id"], data.content)
    )
    post_id = cursor.lastrowid
    c.execute("UPDATE users SET posts_count = posts_count+1 WHERE id=?", (current_user["id"],))
    c.commit()
    post = c.execute("SELECT * FROM posts WHERE id=?", (post_id,)).fetchone()
    c.close()
    return {
        "id": post["id"],
        "content": post["content"],
        "created_at": post["created_at"],
        "likes_count": 0,
        "comments_count": 0,
    }


@app.post("/posts/{post_id}/like")
async def like_post(post_id: int, current_user: dict = Depends(get_current_user)):
    c = db()
    c.execute(
        "INSERT OR IGNORE INTO likes (user_id, post_id) VALUES (?,?)",
        (current_user["id"], post_id)
    )
    c.execute("UPDATE posts SET likes_count = likes_count+1 WHERE id=?", (post_id,))
    c.commit()
    c.close()
    return {"ok": True}


@app.delete("/posts/{post_id}/like")
async def unlike_post(post_id: int, current_user: dict = Depends(get_current_user)):
    c = db()
    c.execute(
        "DELETE FROM likes WHERE user_id=? AND post_id=?",
        (current_user["id"], post_id)
    )
    c.execute("UPDATE posts SET likes_count = MAX(0, likes_count-1) WHERE id=?", (post_id,))
    c.commit()
    c.close()
    return {"ok": True}


@app.post("/posts/{post_id}/comments")
async def add_comment(post_id: int, data: CommentModel, current_user: dict = Depends(get_current_user)):
    c = db()
    c.execute(
        "INSERT INTO comments (user_id, post_id, content) VALUES (?,?,?)",
        (current_user["id"], post_id, data.content)
    )
    c.execute("UPDATE posts SET comments_count = comments_count+1 WHERE id=?", (post_id,))
    c.commit()
    c.close()
    return {"ok": True}


# ════════════════════════════
#  WEBSOCKET (ChatterBox)
# ════════════════════════════

# ════════════════════════════
#  MESSAGES / DMs
# ════════════════════════════

def init_messages_db():
    c = db()
    c.execute("""
        CREATE TABLE IF NOT EXISTS conversations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user1_id INTEGER NOT NULL,
            user2_id INTEGER NOT NULL,
            created_at TEXT DEFAULT (datetime('now')),
            UNIQUE(user1_id, user2_id)
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_id INTEGER NOT NULL,
            sender_id INTEGER NOT NULL,
            content TEXT NOT NULL,
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (conversation_id) REFERENCES conversations(id)
        )
    """)
    c.commit()
    c.close()

init_messages_db()


@app.get("/conversations")
async def get_conversations(current_user: dict = Depends(get_current_user)):
    c = db()
    convos = c.execute("""
        SELECT cv.id, cv.user1_id, cv.user2_id,
               u.username, u.first_name, u.last_name,
               m.content as last_message, m.created_at as last_time
        FROM conversations cv
        JOIN users u ON u.id = CASE
            WHEN cv.user1_id = ? THEN cv.user2_id
            ELSE cv.user1_id
        END
        LEFT JOIN messages m ON m.id = (
            SELECT id FROM messages
            WHERE conversation_id = cv.id
            ORDER BY created_at DESC LIMIT 1
        )
        WHERE cv.user1_id = ? OR cv.user2_id = ?
        ORDER BY m.created_at DESC
    """, (current_user["id"], current_user["id"], current_user["id"])).fetchall()
    c.close()
    return [
        {
            "id": cv["id"],
            "name": f"{cv['first_name']} {cv['last_name']}",
            "username": cv["username"],
            "last_message": cv["last_message"] or "",
            "time": cv["last_time"] or "",
        }
        for cv in convos
    ]


@app.post("/conversations/{user_id}/start")
async def start_conversation(user_id: int, current_user: dict = Depends(get_current_user)):
    c = db()
    u1 = min(current_user["id"], user_id)
    u2 = max(current_user["id"], user_id)
    c.execute(
        "INSERT OR IGNORE INTO conversations (user1_id, user2_id) VALUES (?,?)",
        (u1, u2)
    )
    c.commit()
    convo = c.execute(
        "SELECT id FROM conversations WHERE user1_id=? AND user2_id=?",
        (u1, u2)
    ).fetchone()
    c.close()
    return {"id": convo["id"]}


@app.get("/conversations/{convo_id}/messages")
async def get_messages(convo_id: int, current_user: dict = Depends(get_current_user)):
    c = db()
    msgs = c.execute("""
        SELECT m.*, u.username, u.first_name, u.last_name
        FROM messages m
        JOIN users u ON u.id = m.sender_id
        WHERE m.conversation_id = ?
        ORDER BY m.created_at ASC
    """, (convo_id,)).fetchall()
    c.close()
    return [
        {
            "id": m["id"],
            "content": m["content"],
            "created_at": m["created_at"],
            "is_mine": m["sender_id"] == current_user["id"],
            "sender": f"{m['first_name']} {m['last_name']}",
        }
        for m in msgs
    ]


@app.post("/conversations/{convo_id}/messages")
async def send_message(convo_id: int, data: CommentModel, current_user: dict = Depends(get_current_user)):
    c = db()
    c.execute(
        "INSERT INTO messages (conversation_id, sender_id, content) VALUES (?,?,?)",
        (convo_id, current_user["id"], data.content)
    )
    c.commit()
    c.close()
    return {"ok": True}

active_connections: list[WebSocket] = []

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    active_connections.append(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            for connection in active_connections:
                await connection.send_text(data)
    except WebSocketDisconnect:
        active_connections.remove(websocket)