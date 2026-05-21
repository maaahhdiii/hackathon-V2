import logging
import os
import threading
import time
from pathlib import Path

from flask import Flask, jsonify, render_template_string, request, send_from_directory
from flask_cors import CORS
from werkzeug.exceptions import HTTPException
from werkzeug.utils import secure_filename

app = Flask(__name__)
CORS(app)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("file-service")

SERVICE_NAME = "file"
MAX_HP = 30
APP_FILES_DIR = Path("/app/files")
HACKATHON_SECRET = os.getenv("HACKATHON_SECRET", "HACKATHON_SECRET_2025")
DISALLOWED_EXECUTABLE_EXTS = {".php", ".sh", ".py", ".rb", ".pl", ".exe", ".bat"}

state_lock = threading.Lock()
current_hp = MAX_HP
damage_window = []
vulnerabilities = {
    "path_traversal": False,
    "exec_upload": False,
}

VULN_ALIAS = {
    "sql_injection": "path_traversal",
    "xss": "path_traversal",
    "csrf": "path_traversal",
    "rce": "exec_upload",
    "auth_bypass": "path_traversal",
}


def init_files() -> None:
    APP_FILES_DIR.mkdir(parents=True, exist_ok=True)
    sample = APP_FILES_DIR / "sample.txt"
    report = APP_FILES_DIR / "report.txt"
    if not sample.exists():
        sample.write_text("This is a sample file for the hackathon platform.\n", encoding="utf-8")
    if not report.exists():
        report.write_text("This is a fake report file used for the cyber battle challenge.\n", encoding="utf-8")


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
    return "path_traversal"


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
    <title>File Service UI</title>
    <style>
        body { font-family: Consolas, monospace; background: #0f172a; color: #e2e8f0; margin: 0; padding: 16px; }
        .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 12px; }
        .card { background: #111827; border: 1px solid #334155; border-radius: 8px; padding: 12px; }
        input, select, button { width: 100%; margin-top: 6px; margin-bottom: 8px; padding: 6px; background: #020617; color: #e2e8f0; border: 1px solid #334155; border-radius: 6px; }
        button { cursor: pointer; background: #1d4ed8; }
        pre { background: #020617; border: 1px solid #334155; border-radius: 6px; padding: 8px; min-height: 120px; white-space: pre-wrap; }
    </style>
</head>
<body>
    <h2>File Vulnerable Service</h2>
    <div class="grid">
        <div class="card">
            <h3>Health and HP</h3>
            <input id="secret" placeholder="HACKATHON_SECRET" value="HACKATHON_SECRET_2025" />
            <button onclick="callApi('GET','/health')">Get Health</button>
            <input id="amount" type="number" value="5" />
            <button onclick="callApi('POST','/damage',{secret:val('secret'),amount:num('amount')})">Damage</button>
            <button onclick="callApi('POST','/heal',{secret:val('secret'),amount:num('amount')})">Heal</button>
        </div>
        <div class="card">
            <h3>Vulnerabilities</h3>
            <select id="vuln">
                <option value="path_traversal">path_traversal</option>
                <option value="exec_upload">exec_upload</option>
            </select>
            <button onclick="callApi('POST','/flags/activate',{secret:val('secret'),vuln:val('vuln')})">Activate</button>
            <button onclick="callApi('POST','/flags/deactivate',{secret:val('secret'),vuln:val('vuln')})">Deactivate</button>
            <button onclick="callApi('POST','/defend',{vulnerability_type:val('vuln'),action:'disable'})">Defend Disable</button>
        </div>
        <div class="card">
            <h3>File Operations</h3>
            <button onclick="callApi('GET','/list')">List Files</button>
            <input id="fileName" value="sample.txt" />
            <button onclick="callApi('GET','/download?file='+encodeURIComponent(val('fileName')))">Download</button>
            <input id="uploadFile" type="file" />
            <button onclick="upload()">Upload</button>
        </div>
    </div>
    <pre id="out">Ready.</pre>
    <script>
        const out = document.getElementById('out');
        const val = (id) => document.getElementById(id).value;
        const num = (id) => Number(document.getElementById(id).value || 0);
        async function callApi(method, path, body) {
            const opts = { method, headers: {} };
            if (body !== undefined) { opts.headers['Content-Type'] = 'application/json'; opts.body = JSON.stringify(body); }
            const r = await fetch(path, opts);
            const t = await r.text();
            out.textContent = method + ' ' + path + '\n' + t;
        }
        async function upload() {
            const f = document.getElementById('uploadFile').files[0];
            if (!f) { out.textContent = 'Choose a file first'; return; }
            const fd = new FormData();
            fd.append('file', f);
            const r = await fetch('/upload', { method: 'POST', body: fd });
            out.textContent = 'POST /upload\n' + await r.text();
        }
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
    return jsonify(
        {
            "ok": False,
            "error": "attack shortcut disabled",
            "message": "Use the vulnerable file endpoints directly instead of /attack.",
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


@app.get("/download")
def download():
    requested = request.args.get("file", "")
    if not requested:
        return jsonify({"error": "file parameter is required"}), 400

    if vulnerabilities["path_traversal"]:
        target_path = Path(requested)
    else:
        raw_target = (APP_FILES_DIR / requested).resolve()
        base = APP_FILES_DIR.resolve()
        if not str(raw_target).startswith(str(base)):
            return jsonify({"error": "forbidden"}), 403
        safe_name = os.path.basename(requested)
        target_path = (APP_FILES_DIR / safe_name).resolve()

    if not target_path.exists() or not target_path.is_file():
        return jsonify({"error": "file not found"}), 404

    return app.response_class(target_path.read_text(encoding="utf-8", errors="replace"), mimetype="text/plain")


@app.post("/upload")
def upload():
    if "file" not in request.files:
        return jsonify({"error": "missing file field"}), 400

    uploaded = request.files["file"]
    filename = secure_filename(uploaded.filename or "")
    if not filename:
        return jsonify({"error": "invalid filename"}), 400

    ext = Path(filename).suffix.lower()
    if not vulnerabilities["exec_upload"] and ext in DISALLOWED_EXECUTABLE_EXTS:
        return jsonify({"error": "executable uploads are not allowed"}), 400

    APP_FILES_DIR.mkdir(parents=True, exist_ok=True)
    save_path = APP_FILES_DIR / filename
    uploaded.save(save_path)
    return jsonify({"ok": True, "filename": filename, "path": f"files/{filename}"})


@app.get("/files/<path:filename>")
def serve_file(filename: str):
    return send_from_directory(APP_FILES_DIR, filename)


@app.get("/list")
def list_files():
    APP_FILES_DIR.mkdir(parents=True, exist_ok=True)
    names = sorted([entry.name for entry in APP_FILES_DIR.iterdir() if entry.is_file()])
    return jsonify({"files": names})


if __name__ == "__main__":
    init_files()
    app.run(host="0.0.0.0", port=8003)
