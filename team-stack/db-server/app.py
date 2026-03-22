import logging
import os
import sqlite3
import threading
import time
from pathlib import Path

from flask import Flask, jsonify, request
from flask_cors import CORS
from werkzeug.exceptions import HTTPException

app = Flask(__name__)
CORS(app)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("db-service")

SERVICE_NAME = "db"
MAX_HP = 30
DB_PATH = Path("/app/db.sqlite")
HACKATHON_SECRET = os.getenv("HACKATHON_SECRET", "HACKATHON_SECRET_2025")

state_lock = threading.Lock()
current_hp = MAX_HP
damage_window = []
vulnerabilities = {
    "sqli": False,
    "priv_esc": False,
}

VULN_ALIAS = {
    "sql_injection": "sqli",
    "xss": "priv_esc",
    "csrf": "priv_esc",
    "rce": "priv_esc",
    "auth_bypass": "priv_esc",
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
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            role TEXT NOT NULL
        )
        """
    )
    cur.execute("SELECT COUNT(1) FROM users")
    if cur.fetchone()[0] == 0:
        users = [
            (1, "alice", "user"),
            (2, "bob", "admin"),
            (3, "charlie", "user"),
            (4, "diana", "user"),
            (5, "eve", "user"),
            (6, "frank", "admin"),
            (7, "grace", "user"),
            (8, "heidi", "user"),
            (9, "ivan", "admin"),
            (10, "judy", "user"),
        ]
        cur.executemany("INSERT INTO users (id, name, role) VALUES (?, ?, ?)", users)
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


def normalize_vuln(vuln: str) -> str:
    key = str(vuln or "").strip().lower()
    key = VULN_ALIAS.get(key, key)
    if key in vulnerabilities:
        return key
    return "sqli"


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
    hp_value = apply_damage(int(payload.get("amount", 0)))
    return jsonify({"ok": True, "hp": hp_value})


@app.post("/heal")
def heal():
    payload = request.get_json(silent=True) or {}
    if not verify_secret(payload):
        return jsonify({"ok": False, "error": "unauthorized"}), 401
    hp_value = apply_heal(int(payload.get("amount", 0)))
    return jsonify({"ok": True, "hp": hp_value})


@app.post("/attack")
def attack():
    payload = request.get_json(silent=True) or {}
    vuln = normalize_vuln(payload.get("vulnerability_type") or payload.get("vuln"))
    amount = int(payload.get("amount", 8))

    with state_lock:
        is_active = vulnerabilities.get(vuln, False)

    if not is_active:
        return jsonify({"ok": True, "success": False, "reason": "vulnerability not active", "vuln": vuln, "hp": current_hp})

    hp_value = apply_damage(amount)
    return jsonify({"ok": True, "success": True, "vuln": vuln, "hp": hp_value})


@app.post("/defend")
def defend():
    payload = request.get_json(silent=True) or {}
    vuln = normalize_vuln(payload.get("vulnerability_type") or payload.get("vuln"))
    action = str(payload.get("action", "enable")).strip().lower()
    enabled = action == "enable"

    with state_lock:
        vulnerabilities[vuln] = enabled

    return jsonify({"ok": True, "vuln": vuln, "active": enabled})


@app.post("/query")
def query_users():
    payload = request.get_json(silent=True) or {}
    search = str(payload.get("search", ""))

    conn = get_db_connection()
    cur = conn.cursor()
    if vulnerabilities["sqli"]:
        query = f"SELECT id, name, role FROM users WHERE name LIKE '%{search}%'"
        cur.execute(query)
    else:
        cur.execute("SELECT id, name, role FROM users WHERE name LIKE ?", (f"%{search}%",))
    rows = cur.fetchall()
    conn.close()

    return jsonify({"results": [{"id": row["id"], "name": row["name"], "role": row["role"]} for row in rows]})


@app.get("/user/<int:user_id>")
def get_user(user_id: int):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, name, role FROM users WHERE id = ?", (user_id,))
    row = cur.fetchone()
    conn.close()
    if row is None:
        return jsonify({"error": "user not found"}), 404
    return jsonify({"id": row["id"], "name": row["name"], "role": row["role"]})


@app.post("/user/<int:user_id>/promote")
def promote_user(user_id: int):
    payload = request.get_json(silent=True) or {}
    requester_id = payload.get("requester_id")
    if requester_id is None:
        return jsonify({"error": "requester_id is required"}), 400

    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("SELECT id FROM users WHERE id = ?", (user_id,))
    target = cur.fetchone()
    if target is None:
        conn.close()
        return jsonify({"error": "user not found"}), 404

    if not vulnerabilities["priv_esc"]:
        cur.execute("SELECT role FROM users WHERE id = ?", (requester_id,))
        requester = cur.fetchone()
        if requester is None or requester["role"] != "admin":
            conn.close()
            return jsonify({"error": "forbidden"}), 403

    cur.execute("UPDATE users SET role='admin' WHERE id = ?", (user_id,))
    conn.commit()
    conn.close()
    return jsonify({"ok": True, "user_id": user_id, "new_role": "admin"})


@app.get("/tables")
def list_tables():
    if not vulnerabilities["priv_esc"]:
        return jsonify({"tables": ["users"]})

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    names = [row[0] for row in cur.fetchall()]
    conn.close()
    return jsonify({"tables": names})


if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=8004)
