import os
import re
import threading
import logging

import requests
from flask import Flask, Response, jsonify, render_template, request
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("admin-dashboard")

ORCHESTRATOR_URL = os.getenv("ORCHESTRATOR_URL", "http://127.0.0.1:9000").rstrip("/")
SECRET = os.getenv("HACKATHON_SECRET", "HACKATHON_SECRET_2025")
MAX_TEAMS = int(os.getenv("MAX_TEAMS", os.getenv("TEAM_SLOTS", "10")))


def team_runtime_info(team_no: int):
    return {
        "team_id": team_no,
        "ip": f"team{team_no}-proxy",
        "proxy_port": 9100 + (team_no - 1),
        "ide_port": 8100 + (team_no - 1),
        "name": f"Team {team_no}",
    }


def register_test_teams(count=10, ip_prefix="192.168.1.", ip_start=101, team_prefix="Team", register_mode="proxy_name"):
    results = []
    for idx in range(count):
        team_no = idx + 1
        if register_mode == "proxy_name":
            ip = f"team{team_no}-proxy"
        else:
            ip = f"{ip_prefix}{ip_start + idx}"
        payload = {
            "team_name": f"{team_prefix} {team_no}",
            "ip": ip,
        }
        try:
            resp = requests.post(f"{ORCHESTRATOR_URL}/register", json=payload, timeout=5)
            if resp.ok:
                results.append({"ip": ip, "ok": True})
            else:
                results.append({"ip": ip, "ok": False, "error": resp.text[:180]})
        except Exception as exc:
            results.append({"ip": ip, "ok": False, "error": str(exc)})
    return results


def trigger_battle_start_async():
    def _worker():
        try:
            requests.post(f"{ORCHESTRATOR_URL}/battle/start", timeout=600)
        except Exception as exc:
            log.warning("Async battle start failed: %s", exc)

    thread = threading.Thread(target=_worker, daemon=True)
    thread.start()


def safe_json_response(resp: requests.Response):
    try:
        data = resp.json()
    except Exception:
        data = {"ok": False, "error": "invalid response"}
    return jsonify(data), resp.status_code


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/api/state")
def api_state():
    try:
        resp = requests.get(f"{ORCHESTRATOR_URL}/current", timeout=5)
        return safe_json_response(resp)
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@app.get("/api/teams")
def api_teams():
    try:
        teams_resp = requests.get(f"{ORCHESTRATOR_URL}/teams", timeout=5)
        hp_resp = requests.get(f"{ORCHESTRATOR_URL}/hp", timeout=5)
        scores_resp = requests.get(f"{ORCHESTRATOR_URL}/scores", timeout=5)

        teams_data = teams_resp.json().get("teams", []) if teams_resp.ok else []
        hp_data = hp_resp.json() if hp_resp.ok else {}
        scores_data = scores_resp.json().get("scores", {}) if scores_resp.ok else {}

        merged = []
        for item in teams_data:
            ip = item.get("ip")
            team_id = item.get("team_id")
            proxy_port = item.get("proxy_port")
            ide_port = item.get("ide_port")

            if team_id is None and isinstance(ip, str):
                match = re.match(r"team(\d+)-proxy$", ip)
                if match:
                    team_id = int(match.group(1))

            if proxy_port is None and isinstance(team_id, int) and team_id >= 1:
                proxy_port = 9100 + (team_id - 1)

            if ide_port is None and isinstance(team_id, int) and team_id >= 1:
                ide_port = 8100 + (team_id - 1)

            merged.append(
                {
                    "ip": ip,
                    "name": item.get("name", ip),
                    "team_id": team_id,
                    "proxy_port": proxy_port,
                    "ide_port": ide_port,
                    "hp": hp_data.get(ip, {}),
                    "score": scores_data.get(ip, {}),
                }
            )

        return jsonify({"teams": merged})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@app.post("/api/teams/rename")
def api_rename_team():
    payload = request.get_json(silent=True) or {}
    body = {
        "team_ip": payload.get("team_ip"),
        "name": payload.get("name"),
        "secret": SECRET,
    }
    try:
        resp = requests.post(f"{ORCHESTRATOR_URL}/admin/rename_team", json=body, timeout=5)
        return safe_json_response(resp)
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@app.delete("/api/teams/<path:team_ip>")
def api_delete_team(team_ip):
    body = {"team_ip": team_ip, "secret": SECRET}
    try:
        resp = requests.delete(f"{ORCHESTRATOR_URL}/admin/remove_team", json=body, timeout=5)
        return safe_json_response(resp)
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@app.post("/api/teams/<path:team_ip>/hp")
def api_set_hp(team_ip):
    payload = request.get_json(silent=True) or {}
    body = {
        "team_ip": team_ip,
        "service": payload.get("service"),
        "hp": payload.get("hp"),
        "secret": SECRET,
    }
    try:
        resp = requests.post(f"{ORCHESTRATOR_URL}/admin/set_hp", json=body, timeout=5)
        return safe_json_response(resp)
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@app.post("/api/teams/<path:team_ip>/score")
def api_set_score(team_ip):
    payload = request.get_json(silent=True) or {}
    body = {
        "team_ip": team_ip,
        "score": payload.get("score"),
        "secret": SECRET,
    }
    try:
        resp = requests.post(f"{ORCHESTRATOR_URL}/admin/set_score", json=body, timeout=5)
        return safe_json_response(resp)
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@app.post("/api/battle/start")
def api_start_battle():
    try:
        resp = requests.post(f"{ORCHESTRATOR_URL}/battle/start", timeout=10)
        return safe_json_response(resp)
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@app.post("/api/battle/stop")
def api_stop_battle():
    try:
        resp = requests.post(f"{ORCHESTRATOR_URL}/battle/stop", timeout=10)
        return safe_json_response(resp)
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@app.post("/api/teams/add_bulk")
def api_add_bulk_teams():
    payload = request.get_json(silent=True) or {}
    count = int(payload.get("count", 10))
    ip_prefix = str(payload.get("ip_prefix", "192.168.1."))
    ip_start = int(payload.get("ip_start", 101))
    team_prefix = str(payload.get("team_prefix", "Team"))
    register_mode = str(payload.get("register_mode", "proxy_name")).strip().lower()

    if register_mode not in ("proxy_name", "ip"):
        return jsonify({"ok": False, "error": "register_mode must be 'proxy_name' or 'ip'"}), 400

    count = max(1, min(50, count))
    results = register_test_teams(
        count=count,
        ip_prefix=ip_prefix,
        ip_start=ip_start,
        team_prefix=team_prefix,
        register_mode=register_mode,
    )
    ok_count = sum(1 for item in results if item.get("ok"))

    return jsonify({
        "ok": True,
        "requested": count,
        "registered": ok_count,
        "results": results,
    })


@app.post("/api/teams/add_one")
def api_add_one_team():
    payload = request.get_json(silent=True) or {}

    team_no = payload.get("team_no")
    team_name = str(payload.get("team_name", "")).strip()

    try:
        team_no = int(team_no)
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": "team_no must be an integer"}), 400

    if team_no < 1 or team_no > MAX_TEAMS:
        return jsonify({"ok": False, "error": f"team_no must be between 1 and {MAX_TEAMS}"}), 400

    info = team_runtime_info(team_no)
    payload_register = {
        "team_name": team_name or info["name"],
        "ip": info["ip"],
        "team_id": info["team_id"],
        "proxy_port": info["proxy_port"],
        "ide_port": info["ide_port"],
    }

    try:
        resp = requests.post(f"{ORCHESTRATOR_URL}/register", json=payload_register, timeout=5)
        data = resp.json() if resp.content else {}
        if not resp.ok:
            return jsonify({"ok": False, "error": data.get("error", "register failed")}), resp.status_code
        return jsonify({"ok": True, "team": payload_register})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@app.post("/api/battle/hackathon_day_start")
def api_hackathon_day_start():
    payload = request.get_json(silent=True) or {}
    count = int(payload.get("count", 10))
    ip_prefix = str(payload.get("ip_prefix", "192.168.1."))
    ip_start = int(payload.get("ip_start", 101))
    team_prefix = str(payload.get("team_prefix", "Team"))
    register_mode = str(payload.get("register_mode", "proxy_name")).strip().lower()

    if register_mode not in ("proxy_name", "ip"):
        return jsonify({"ok": False, "error": "register_mode must be 'proxy_name' or 'ip'"}), 400

    count = max(1, min(50, count))
    register_results = register_test_teams(
        count=count,
        ip_prefix=ip_prefix,
        ip_start=ip_start,
        team_prefix=team_prefix,
        register_mode=register_mode,
    )
    ok_count = sum(1 for item in register_results if item.get("ok"))

    trigger_battle_start_async()

    return jsonify({
        "ok": True,
        "registered": ok_count,
        "results": register_results,
        "battle": {"queued": True, "message": "battle start triggered asynchronously"},
    })


@app.get("/api/events")
def api_events():
    try:
        resp = requests.get(f"{ORCHESTRATOR_URL}/events", timeout=5)
        return safe_json_response(resp)
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@app.get("/stream")
def api_stream_proxy():
    def generate():
        while True:
            try:
                with requests.get(f"{ORCHESTRATOR_URL}/stream", stream=True, timeout=65) as upstream:
                    for line in upstream.iter_lines(decode_unicode=True):
                        if line is None:
                            continue
                        if line:
                            yield f"{line}\n"
                        else:
                            yield "\n"
            except Exception:
                yield "event: ping\ndata: {\"ok\": false}\n\n"
    return Response(generate(), mimetype="text/event-stream")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=4000, threaded=True)
