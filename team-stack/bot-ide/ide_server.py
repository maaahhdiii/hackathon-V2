import json
import os
import re
import subprocess
import threading
from pathlib import Path

import requests
from flask import Flask, Response, jsonify, render_template, request
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

TEAM_ID = os.getenv("TEAM_ID", "1")
TEAM_NAME = os.getenv("TEAM_NAME", "Team 1")
ORCHESTRATOR_URL = os.getenv("ORCHESTRATOR_URL", "http://orchestrator:9000")
SECRET = os.getenv("HACKATHON_SECRET", "HACKATHON_SECRET_2025")
MY_PROXY_PORT = os.getenv("MY_PROXY_PORT", "9100")
SERVER_IP = os.getenv("SERVER_IP", "192.168.1.100")
DISCOVERY_HOST = os.getenv("DISCOVERY_HOST", SERVER_IP)
DISCOVERY_PORT_MIN = int(os.getenv("DISCOVERY_PORT_MIN", "12000"))
DISCOVERY_PORT_MAX = int(os.getenv("DISCOVERY_PORT_MAX", "12999"))
MY_PROXY_INTERNAL = os.getenv("MY_PROXY_INTERNAL", f"http://team{TEAM_ID}-proxy")
WORKSPACE = Path("/app/workspace")

processes = {"attacker": None, "defender": None}
output_logs = {"attacker": [], "defender": []}


def _java_cmd(path: str):
    classname = Path(path).stem
    return ["bash", "-lc", f"javac '{path}' && java -cp '{WORKSPACE}' {classname}"]


def _c_cmd(path: str):
    binary = str(Path(path).with_suffix(""))
    return ["bash", "-lc", f"gcc '{path}' -o '{binary}' && '{binary}'"]


def _cpp_cmd(path: str):
    binary = str(Path(path).with_suffix(""))
    return ["bash", "-lc", f"g++ '{path}' -o '{binary}' && '{binary}'"]


LANGUAGE_RUNNERS = {
    "py": lambda f: ["python3", "-u", f],
    "js": lambda f: ["node", f],
    "go": lambda f: ["go", "run", f],
    "java": _java_cmd,
    "c": _c_cmd,
    "cpp": _cpp_cmd,
    "sh": lambda f: ["bash", f],
}


def get_extension(filename: str) -> str:
    return filename.rsplit(".", 1)[-1].lower() if "." in filename else "py"


def append_log(bot_name: str, line: str):
    output_logs.setdefault(bot_name, [])
    output_logs[bot_name].append(line)
    if len(output_logs[bot_name]) > 500:
        output_logs[bot_name] = output_logs[bot_name][-500:]


def stream_output(proc: subprocess.Popen, bot_name: str):
    output_logs[bot_name] = []
    try:
        for raw in iter(proc.stdout.readline, b""):
            if not raw:
                break
            decoded = raw.decode("utf-8", errors="replace")
            append_log(bot_name, decoded)
    except Exception as exc:
        append_log(bot_name, f"[stream error] {exc}\n")


@app.get("/")
def index():
    return render_template(
        "ide.html",
        team_id=TEAM_ID,
        team_name=TEAM_NAME,
        orchestrator_url=ORCHESTRATOR_URL,
        my_proxy_port=MY_PROXY_PORT,
        server_ip=SERVER_IP,
    )


@app.get("/api/files")
def list_files():
    try:
        files = [f.name for f in WORKSPACE.iterdir() if f.is_file()]
        return jsonify({"files": sorted(files)})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.get("/api/files/<filename>")
def read_file(filename):
    path = WORKSPACE / Path(filename).name
    try:
        return jsonify({"filename": path.name, "content": path.read_text(encoding="utf-8")})
    except FileNotFoundError:
        return jsonify({"error": "file not found"}), 404
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.post("/api/files/<filename>")
def save_file(filename):
    path = WORKSPACE / Path(filename).name
    data = request.get_json(silent=True) or {}
    try:
        path.write_text(data.get("content", ""), encoding="utf-8")
        return jsonify({"ok": True, "filename": path.name})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


def stop_existing(bot_name: str):
    proc = processes.get(bot_name)
    if proc and proc.poll() is None:
        try:
            proc.kill()
        except Exception:
            pass
    processes[bot_name] = None


@app.post("/api/run/<bot_name>")
def run_bot(bot_name):
    if bot_name not in ("attacker", "defender"):
        return jsonify({"error": "invalid bot name"}), 400

    payload = request.get_json(silent=True) or {}
    filename = payload.get("filename", f"{bot_name}.py")
    filepath = WORKSPACE / Path(filename).name
    if not filepath.exists():
        return jsonify({"error": f"file not found: {filename}"}), 404

    stop_existing(bot_name)

    ext = get_extension(filepath.name)
    cmd_builder = LANGUAGE_RUNNERS.get(ext)
    if not cmd_builder:
        return jsonify({"error": f"unsupported extension: {ext}"}), 400

    env = os.environ.copy()
    my_target_external = f"http://{SERVER_IP}:{MY_PROXY_PORT}"
    env.update(
        {
            "ORCHESTRATOR_URL": ORCHESTRATOR_URL,
            "HACKATHON_SECRET": SECRET,
            "MY_PROXY_PORT": MY_PROXY_PORT,
            "SERVER_IP": SERVER_IP,
            "DISCOVERY_HOST": DISCOVERY_HOST,
            "DISCOVERY_PORT_MIN": str(DISCOVERY_PORT_MIN),
            "DISCOVERY_PORT_MAX": str(DISCOVERY_PORT_MAX),
            "TEAM_ID": TEAM_ID,
            "TEAM_NAME": TEAM_NAME,
            "MY_TARGET": MY_PROXY_INTERNAL,
            "MY_TARGET_INTERNAL": MY_PROXY_INTERNAL,
            "MY_TARGET_EXTERNAL": my_target_external,
            "ORCH": ORCHESTRATOR_URL,
        }
    )

    try:
        proc = subprocess.Popen(
            cmd_builder(str(filepath)),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            cwd=str(WORKSPACE),
            env=env,
        )
        processes[bot_name] = proc
        output_logs[bot_name] = []
        threading.Thread(target=stream_output, args=(proc, bot_name), daemon=True).start()
        return jsonify({"ok": True, "bot": bot_name, "filename": filepath.name, "pid": proc.pid})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.post("/api/stop/<bot_name>")
def stop_bot(bot_name):
    if bot_name not in ("attacker", "defender"):
        return jsonify({"error": "invalid bot name"}), 400
    was_running = processes.get(bot_name) is not None and processes[bot_name].poll() is None
    stop_existing(bot_name)
    return jsonify({"ok": True, "bot": bot_name, "was_running": was_running})


@app.get("/api/logs/<bot_name>")
def get_logs(bot_name):
    proc = processes.get(bot_name)
    running = proc is not None and proc.poll() is None
    return jsonify({"logs": output_logs.get(bot_name, []), "running": running})


@app.get("/api/status")
def status():
    bots = {}
    for name in ("attacker", "defender"):
        proc = processes.get(name)
        bots[name] = {"running": proc is not None and proc.poll() is None, "pid": proc.pid if proc else None}
    return jsonify({"team_id": TEAM_ID, "team_name": TEAM_NAME, "bots": bots})


@app.get("/api/context")
def context():
    return jsonify(
        {
            "team_id": TEAM_ID,
            "team_name": TEAM_NAME,
            "my_proxy": f"http://{SERVER_IP}:{MY_PROXY_PORT}",
            "my_proxy_internal": MY_PROXY_INTERNAL,
            "orchestrator": ORCHESTRATOR_URL,
            "server_ip": SERVER_IP,
            "discovery_host": DISCOVERY_HOST,
            "discovery_port_min": DISCOVERY_PORT_MIN,
            "discovery_port_max": DISCOVERY_PORT_MAX,
            "active_service_url": f"{ORCHESTRATOR_URL}/current",
            "events_url": f"{ORCHESTRATOR_URL}/events",
            "submit_flag_url": f"{ORCHESTRATOR_URL}/submit_flag",
        }
    )


if __name__ == "__main__":
    WORKSPACE.mkdir(parents=True, exist_ok=True)
    app.run(host="0.0.0.0", port=8080, debug=False, threaded=True)
