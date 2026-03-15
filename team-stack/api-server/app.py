import logging
import os
import subprocess
import threading
import time

from flask import Flask, jsonify, request
from flask_cors import CORS
from werkzeug.exceptions import HTTPException

app = Flask(__name__)
CORS(app)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("api-service")

SERVICE_NAME = "api"
MAX_HP = 30
HACKATHON_SECRET = os.getenv("HACKATHON_SECRET", "HACKATHON_SECRET_2025")

state_lock = threading.Lock()
current_hp = MAX_HP
damage_window = []
vulnerabilities = {
    "insecure_ep": False,
    "cmd_inject": False,
    "idor": False,
}

users = [
    {"id": 1, "name": "alice", "email": "alice@example.com", "role": "user"},
    {"id": 2, "name": "bob", "email": "bob@example.com", "role": "admin"},
    {"id": 3, "name": "charlie", "email": "charlie@example.com", "role": "user"},
    {"id": 4, "name": "diana", "email": "diana@example.com", "role": "user"},
    {"id": 5, "name": "eve", "email": "eve@example.com", "role": "user"},
]


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


def get_user(user_id: int):
    return next((u for u in users if u["id"] == user_id), None)


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


@app.get("/users")
def list_users():
    if not vulnerabilities["insecure_ep"]:
        auth = request.headers.get("Authorization", "")
        if auth != "Bearer admin-token-2025":
            return jsonify({"error": "unauthorized"}), 401
    return jsonify({"users": [{"id": u["id"], "name": u["name"], "role": u["role"]} for u in users]})


@app.get("/users/<int:user_id>")
def user_by_id(user_id: int):
    user = get_user(user_id)
    if user is None:
        return jsonify({"error": "user not found"}), 404

    if not vulnerabilities["idor"]:
        requester = request.headers.get("X-User-Id", "")
        try:
            requester_id = int(requester)
        except ValueError:
            return jsonify({"error": "missing or invalid X-User-Id"}), 400
        if requester_id != user_id:
            return jsonify({"error": "forbidden"}), 403

    return jsonify({"id": user["id"], "name": user["name"], "email": user["email"], "role": user["role"]})


@app.post("/run")
def run_command():
    payload = request.get_json(silent=True) or {}
    cmd = str(payload.get("cmd", "")).strip()
    if not cmd:
        return jsonify({"error": "cmd is required"}), 400

    if vulnerabilities["cmd_inject"]:
        output = os.popen(cmd).read()
        return jsonify({"output": output.strip()})

    command_map = {
        "ping": ["ping", "-c", "1", "127.0.0.1"],
        "whoami": ["whoami"],
        "date": ["date"],
        "uptime": ["uptime"],
    }
    if cmd not in command_map:
        return jsonify({"error": "command not allowed"}), 400

    result = subprocess.run(command_map[cmd], capture_output=True, text=True, check=False, timeout=5)
    output = (result.stdout or result.stderr).strip()
    return jsonify({"output": output})


@app.get("/admin")
def admin_panel():
    if not vulnerabilities["insecure_ep"]:
        key = request.headers.get("X-Admin-Key", "")
        if key != "admin-secret-2025":
            return jsonify({"error": "unauthorized"}), 401
    return jsonify({"message": "welcome admin", "users_count": len(users), "server": "api"})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8002)
