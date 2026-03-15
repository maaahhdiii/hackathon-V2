import html
import logging
import os
import sqlite3
import threading
import time
from pathlib import Path

import jwt
from flask import Flask, jsonify, request
from flask_cors import CORS
from werkzeug.exceptions import HTTPException

app = Flask(__name__)
CORS(app)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("web-service")

SERVICE_NAME = "web"
MAX_HP = 40
DB_PATH = Path("/app/web.db")
HACKATHON_SECRET = os.getenv("HACKATHON_SECRET", "HACKATHON_SECRET_2025")
JWT_SIGNING_SECRET = "SUPER_SECRET_KEY_2025"

state_lock = threading.Lock()
current_hp = MAX_HP
damage_window = []
vulnerabilities = {
    "sqli": False,
    "xss": False,
    "auth_bypass": False,
}


def get_db_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            password TEXT NOT NULL
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS comments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            content TEXT NOT NULL,
            created_at INTEGER NOT NULL
        )
        """
    )
    cur.execute("SELECT id FROM users WHERE username = ?", ("admin",))
    if cur.fetchone() is None:
        cur.execute("INSERT INTO users (username, password) VALUES (?, ?)", ("admin", "secret123"))
    conn.commit()
    conn.close()


def status_from_hp(hp_value: int) -> str:
    if hp_value == 0:
        return "offline"
    if hp_value > MAX_HP * 0.5:
        return "online"
    return "degraded"


def verify_secret(payload: dict) -> bool:
    return payload.get("secret") == HACKATHON_SECRET


def apply_damage(amount: int) -> int:
    global current_hp
    now = int(time.time())
    with state_lock:
        valid = []
        used = 0
        for ts, val in damage_window:
            if now - ts <= 30:
                valid.append((ts, val))
                used += val
        damage_window.clear()
        damage_window.extend(valid)

        allowed = max(0, 15 - used)
        applied = max(0, min(int(amount), allowed))
        current_hp = max(0, current_hp - applied)
        if applied > 0:
            damage_window.append((now, applied))
        return current_hp


def apply_heal(amount: int) -> int:
    global current_hp
    with state_lock:
        current_hp = min(MAX_HP, current_hp + max(0, int(amount)))
        return current_hp


@app.errorhandler(Exception)
def handle_exception(error):
    code = 500
    message = "internal server error"
    if isinstance(error, HTTPException):
        code = error.code or 500
        message = error.description
    log.exception("Request failed: %s", error)
    return jsonify({"ok": False, "error": message}), code


@app.get("/health")
def health():
    with state_lock:
        hp_value = current_hp
        active = [k for k, v in vulnerabilities.items() if v]
    return jsonify(
        {
            "service": SERVICE_NAME,
            "status": status_from_hp(hp_value),
            "hp": hp_value,
            "max_hp": MAX_HP,
            "vulns_active": active,
            "timestamp": int(time.time()),
        }
    )


@app.post("/flags/activate")
def activate_flag():
    payload = request.get_json(silent=True) or {}
    if not verify_secret(payload):
        return jsonify({"ok": False, "error": "unauthorized"}), 401
    vuln = payload.get("vuln")
    with state_lock:
        if vuln not in vulnerabilities:
            return jsonify({"ok": False, "error": "unknown vuln"}), 400
        vulnerabilities[vuln] = True
    return jsonify({"ok": True, "vuln": vuln, "active": True})


@app.post("/flags/deactivate")
def deactivate_flag():
    payload = request.get_json(silent=True) or {}
    if not verify_secret(payload):
        return jsonify({"ok": False, "error": "unauthorized"}), 401
    vuln = payload.get("vuln")
    with state_lock:
        if vuln not in vulnerabilities:
            return jsonify({"ok": False, "error": "unknown vuln"}), 400
        vulnerabilities[vuln] = False
    return jsonify({"ok": True, "vuln": vuln, "active": False})


@app.post("/damage")
def damage():
    payload = request.get_json(silent=True) or {}
    if not verify_secret(payload):
        return jsonify({"ok": False, "error": "unauthorized"}), 401
    amount = int(payload.get("amount", 0))
    hp_value = apply_damage(amount)
    return jsonify({"ok": True, "hp": hp_value})


@app.post("/heal")
def heal():
    payload = request.get_json(silent=True) or {}
    if not verify_secret(payload):
        return jsonify({"ok": False, "error": "unauthorized"}), 401
    amount = int(payload.get("amount", 0))
    hp_value = apply_heal(amount)
    return jsonify({"ok": True, "hp": hp_value})


@app.post("/login")
def login():
    payload = request.get_json(silent=True) or request.form.to_dict() or {}
    username = str(payload.get("username", "")).strip()
    password = str(payload.get("password", ""))
    if not username or not password:
        return jsonify({"error": "invalid credentials"}), 401

    conn = get_db_connection()
    cur = conn.cursor()
    if vulnerabilities["sqli"]:
        query = f"SELECT id, username FROM users WHERE username='{username}' AND password='{password}'"
        cur.execute(query)
    else:
        cur.execute("SELECT id, username FROM users WHERE username=? AND password=?", (username, password))
    user = cur.fetchone()
    conn.close()

    if user is None:
        return jsonify({"error": "invalid credentials"}), 401

    token = jwt.encode(
        {"user": user["username"], "role": "admin" if user["username"] == "admin" else "user", "iat": int(time.time())},
        JWT_SIGNING_SECRET,
        algorithm="HS256",
    )
    return jsonify({"token": token})


@app.get("/search")
def search_users():
    term = request.args.get("q", "")
    conn = get_db_connection()
    cur = conn.cursor()
    if vulnerabilities["sqli"]:
        query = f"SELECT id, username FROM users WHERE username LIKE '%{term}%'"
        cur.execute(query)
    else:
        cur.execute("SELECT id, username FROM users WHERE username LIKE ?", (f"%{term}%",))
    rows = cur.fetchall()
    conn.close()
    return jsonify({"results": [{"id": row["id"], "username": row["username"]} for row in rows]})


@app.post("/comment")
def add_comment():
    payload = request.get_json(silent=True) or request.form.to_dict() or {}
    comment = str(payload.get("comment", ""))
    value = comment if vulnerabilities["xss"] else html.escape(comment)

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("INSERT INTO comments (content, created_at) VALUES (?, ?)", (value, int(time.time())))
    conn.commit()
    conn.close()

    return jsonify({"comment": value})


@app.get("/comments")
def list_comments():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT content FROM comments ORDER BY id ASC")
    comments = [row["content"] for row in cur.fetchall()]
    conn.close()

    if vulnerabilities["xss"]:
        return jsonify({"comments": comments})
    return jsonify({"comments": [html.escape(item) for item in comments]})


@app.get("/profile")
def profile():
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return jsonify({"error": "missing bearer token"}), 401

    token = auth_header.split(" ", 1)[1].strip()
    try:
        if vulnerabilities["auth_bypass"]:
            decoded = jwt.decode(token, options={"verify_signature": False, "verify_exp": False})
        else:
            decoded = jwt.decode(token, JWT_SIGNING_SECRET, algorithms=["HS256"])
    except Exception:
        return jsonify({"error": "invalid token"}), 401

    return jsonify({"user": decoded.get("user", "admin"), "role": decoded.get("role", "admin")})


if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=8001)
