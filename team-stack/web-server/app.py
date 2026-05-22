import html
import logging
import os
import sqlite3
import threading
import time
from pathlib import Path
from common.flag_runtime import FlagRuntime

import jwt
from flask import Flask, jsonify, render_template_string, request
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

# Flag runtime for service-side rotating flags
FLAG_RUNTIME = FlagRuntime("web")

VULN_ALIAS = {
    "sql_injection": "sqli",
    "csrf": "auth_bypass",
    "rce": "auth_bypass",
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


@app.get("/")
def service_ui():
        return render_template_string(
                """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Web Service Tactical Console</title>
    <style>
        :root {
            --bg: #05080f;
            --panel: rgba(10, 17, 28, 0.94);
            --line: #21344a;
            --text: #d8f7ff;
            --muted: #7ea2be;
            --neon: #00e8c4;
            --blue: #2f83ff;
            --warn: #ffc857;
            --bad: #ff5a7a;
            --ok: #57fca7;
        }

        * { box-sizing: border-box; }

        body {
            margin: 0;
            min-height: 100vh;
            font-family: "Consolas", "Lucida Console", monospace;
            color: var(--text);
            background:
                radial-gradient(circle at 12% 10%, rgba(47, 131, 255, 0.16), transparent 28%),
                radial-gradient(circle at 88% 0%, rgba(0, 232, 196, 0.14), transparent 32%),
                linear-gradient(180deg, #04070d 0%, #07101a 40%, #04070d 100%);
            padding: 16px;
        }

        .scan {
            position: fixed;
            inset: 0;
            pointer-events: none;
            opacity: 0.18;
            background: repeating-linear-gradient(
                to bottom,
                rgba(255,255,255,0.05),
                rgba(255,255,255,0.05) 1px,
                transparent 1px,
                transparent 4px
            );
        }

        .wrap { max-width: 1460px; margin: 0 auto; position: relative; z-index: 1; }

        .head {
            display: flex;
            justify-content: space-between;
            align-items: center;
            gap: 12px;
            flex-wrap: wrap;
            margin-bottom: 12px;
            background: linear-gradient(140deg, rgba(12, 20, 33, 0.96), rgba(8, 14, 24, 0.96));
            border: 1px solid var(--line);
            border-radius: 12px;
            padding: 12px;
            box-shadow: 0 0 22px rgba(47,131,255,0.14), inset 0 0 16px rgba(0,232,196,0.08);
        }

        .title { font-size: clamp(20px, 2.4vw, 34px); letter-spacing: 1px; text-transform: uppercase; color: #cbf8ff; }
        .title small { font-size: 0.5em; color: var(--neon); margin-left: 8px; }

        .chips { display: flex; gap: 8px; flex-wrap: wrap; }
        .chip {
            border: 1px solid #2b4762;
            border-radius: 999px;
            padding: 6px 10px;
            font-size: 12px;
            color: #cde9ff;
            background: rgba(13, 24, 39, 0.92);
        }
        .chip.ok { border-color: rgba(87,252,167,0.65); color: #d6ffe6; }

        .grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; }
        .card {
            background: var(--panel);
            border: 1px solid var(--line);
            border-radius: 12px;
            padding: 12px;
            box-shadow: inset 0 0 14px rgba(47,131,255,0.06);
        }

        h3 { margin: 0 0 8px; text-transform: uppercase; letter-spacing: 1px; color: #a8e7ff; }

        label { display: block; font-size: 12px; color: var(--muted); margin-top: 6px; }

        input, select, button {
            width: 100%;
            margin-top: 6px;
            margin-bottom: 8px;
            padding: 7px 9px;
            border-radius: 8px;
            border: 1px solid #2c4561;
            background: #07101a;
            color: #e2f7ff;
            font-family: inherit;
        }

        button {
            cursor: pointer;
            text-transform: uppercase;
            letter-spacing: 0.7px;
            font-size: 12px;
            font-weight: 700;
            background: linear-gradient(135deg, #1d4f91, #2f83ff);
        }

        .btn-danger { background: linear-gradient(135deg, #7e1d39, #d93a63); }
        .btn-warn { background: linear-gradient(135deg, #7a5200, #d38a00); }
        .btn-good { background: linear-gradient(135deg, #157b5c, #0fb38a); }

        .double { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }

        .vuln-list { display: grid; gap: 8px; margin-bottom: 8px; }
        .vbtn {
            text-align: left;
            border: 1px solid #2f4863;
            border-radius: 8px;
            background: #081323;
            color: #d7f6ff;
            padding: 8px;
            cursor: pointer;
            font-family: inherit;
        }
        .vbtn.active {
            border-color: rgba(0, 232, 196, 0.7);
            background: rgba(0, 232, 196, 0.14);
            color: #cffff1;
            box-shadow: 0 0 12px rgba(0, 232, 196, 0.18);
        }

        .hint { color: var(--muted); font-size: 12px; margin-bottom: 8px; }

        .console {
            margin-top: 12px;
            background: rgba(3, 8, 15, 0.96);
            border: 1px solid #1d344b;
            border-radius: 10px;
            padding: 10px;
            min-height: 180px;
            white-space: pre-wrap;
            color: #bfffe7;
            font-size: 12px;
            line-height: 1.35;
            overflow: auto;
        }

        @media (max-width: 1100px) {
            .grid { grid-template-columns: 1fr; }
        }
    </style>
</head>
<body>
    <div class="scan"></div>
    <div class="wrap">
    <div class="head">
        <div class="title">Web Vulnerable Service <small>tactical panel</small></div>
        <div class="chips">
            <span class="chip">Hackathon Mode</span>
            <span class="chip">Service: WEB</span>
            <span id="healthChip" class="chip ok">Health: --</span>
        </div>
    </div>

    <div class="grid">
        <div class="card">
            <h3>Health and HP</h3>
            <label>Shared Secret</label>
            <input id="secret" placeholder="HACKATHON_SECRET" value="HACKATHON_SECRET_2025" />
            <button class="btn-good" onclick="refreshHealth()">Get Health</button>
            <label>Amount</label>
            <input id="damageAmount" type="number" value="5" />
            <div class="double">
                <button class="btn-danger" onclick="callApi('POST','/damage',{secret:val('secret'),amount:num('damageAmount')})">Damage</button>
                <button class="btn-good" onclick="callApi('POST','/heal',{secret:val('secret'),amount:num('damageAmount')})">Heal</button>
            </div>
        </div>
        <div class="card">
            <h3>Vulnerabilities</h3>
            <div class="hint">Web service exposes 3 challenge vulns: sqli, xss, auth_bypass.</div>
            <div class="vuln-list">
                <button id="vbtn-sqli" class="vbtn active" onclick="setVuln('sqli')">sqli</button>
                <button id="vbtn-xss" class="vbtn" onclick="setVuln('xss')">xss</button>
                <button id="vbtn-auth_bypass" class="vbtn" onclick="setVuln('auth_bypass')">auth_bypass</button>
            </div>
            <div class="hint">Selected: <span id="selectedVulnLabel">sqli</span></div>
            <div class="double">
                <button class="btn-warn" onclick="callApi('POST','/flags/activate',{secret:val('secret'),vuln:selectedVuln})">Activate</button>
                <button class="btn-warn" onclick="callApi('POST','/flags/deactivate',{secret:val('secret'),vuln:selectedVuln})">Deactivate</button>
            </div>
            <div class="double">
                <button onclick="callApi('POST','/defend',{vulnerability_type:selectedVuln,action:'disable'})">Defend Disable</button>
            </div>
        </div>
        <div class="card">
            <h3>App Endpoints</h3>
            <label>Username</label>
            <input id="username" placeholder="username" value="admin" />
            <label>Password</label>
            <input id="password" placeholder="password" value="secret123" />
            <button class="btn-good" onclick="login()">Login</button>
            <label>Search</label>
            <input id="search" placeholder="search term" value="a" />
            <button onclick="callApi('GET','/search?q='+encodeURIComponent(val('search')))">Search Users</button>
            <label>Comment</label>
            <input id="comment" placeholder="comment" value="hello" />
            <button onclick="callApi('POST','/comment',{comment:val('comment')})">Add Comment</button>
            <button onclick="callApi('GET','/comments')">List Comments</button>
            <label>Bearer Token</label>
            <input id="token" placeholder="Bearer token" />
            <button onclick="profile()">Profile</button>
        </div>
    </div>

    <pre id="out" class="console">Ready.</pre>
    </div>
    <script>
        const out = document.getElementById('out');
        const healthChip = document.getElementById('healthChip');
        const selectedVulnLabel = document.getElementById('selectedVulnLabel');
        const val = (id) => document.getElementById(id).value;
        const num = (id) => Number(document.getElementById(id).value || 0);
        const apiBase = window.location.pathname.startsWith('/web/') ? '/web' : '';
        let selectedVuln = 'sqli';

        function writeLog(msg) {
            const now = new Date().toLocaleTimeString();
            out.textContent = `[${now}] ${msg}\n\n` + out.textContent;
        }

        function apiPath(path) {
            if (!path || typeof path !== 'string') return path;
            if (!path.startsWith('/')) return path;
            return apiBase + path;
        }

        function setVuln(v) {
            selectedVuln = v;
            selectedVulnLabel.textContent = v;
            ['sqli', 'xss', 'auth_bypass'].forEach((key) => {
                const el = document.getElementById('vbtn-' + key);
                if (el) el.classList.toggle('active', key === v);
            });
        }

        async function callApi(method, path, body) {
            const fullPath = apiPath(path);
            const opts = { method, headers: {} };
            if (body !== undefined) { opts.headers['Content-Type'] = 'application/json'; opts.body = JSON.stringify(body); }
            try {
                const r = await fetch(fullPath, opts);
                const t = await r.text();
                writeLog(method + ' ' + fullPath + '\n' + t);
                return { ok: r.ok, text: t };
            } catch (err) {
                writeLog(method + ' ' + fullPath + '\n' + 'request error: ' + err.message);
                return { ok: false, text: String(err.message) };
            }
        }

        async function refreshHealth() {
            const r = await fetch(apiPath('/health'));
            const t = await r.text();
            writeLog('GET /health\n' + t);
            try {
                const d = JSON.parse(t);
                healthChip.textContent = `Health: ${d.status || '--'} | HP ${d.hp ?? '--'}/${d.max_hp ?? '--'}`;
                healthChip.className = 'chip ' + ((d.status === 'online' || d.status === 'degraded') ? 'ok' : '');
            } catch (_) {}
        }

        async function login() {
            const res = await callApi('POST', '/login', { username: val('username'), password: val('password') });
            try { const data = JSON.parse(res.text); if (data.token) document.getElementById('token').value = data.token; } catch (_) {}
        }
        async function profile() {
            const token = val('token');
            const r = await fetch(apiPath('/profile'), { headers: { Authorization: 'Bearer ' + token } });
            writeLog('GET /profile\n' + await r.text());
        }

        refreshHealth();
        setInterval(() => { refreshHealth().catch(() => {}); }, 5000);
    </script>
</body>
</html>
                """
        )


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
            "current_flag": FLAG_RUNTIME.current_flag(),
            "timestamp": int(time.time()),
        }
    )


@app.post("/flag/verify")
def verify_flag():
    payload = request.get_json(silent=True) or {}
    flag = payload.get("flag")
    if not flag:
        return jsonify({"ok": False, "error": "flag required"}), 400
    ok = FLAG_RUNTIME.verify(flag)
    return jsonify({"ok": ok})


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


@app.post("/attack")
def attack():
    return jsonify(
        {
            "ok": False,
            "error": "attack shortcut disabled",
            "message": "Use the vulnerable web endpoints directly instead of /attack.",
        }
    ), 410


@app.post("/defend")
def defend():
    payload = request.get_json(silent=True) or {}
    vuln = normalize_vuln(payload.get("vulnerability_type") or payload.get("vuln"))
    action = str(payload.get("action", "enable")).strip().lower()
    enabled = action == "enable"

    with state_lock:
        vulnerabilities[vuln] = enabled

    return jsonify({"ok": True, "vuln": vuln, "active": enabled})


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
