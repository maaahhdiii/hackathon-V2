import json
import logging
import os
import threading
import time
from collections import defaultdict
from typing import Any, Dict, List

import requests
from apscheduler.schedulers.background import BackgroundScheduler
from flask import Flask, Response, jsonify, request
from flask_cors import CORS
from werkzeug.exceptions import HTTPException

app = Flask(__name__)
CORS(app)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("orchestrator")

SECRET = os.getenv("HACKATHON_SECRET", "HACKATHON_SECRET_2025")
SLOTS = ["web", "api", "file", "db"]
SLOT_DURATION = int(os.getenv("SLOT_DURATION", "450"))
MAX_HP = {"web": 40, "api": 30, "file": 30, "db": 30}
VULNS = {
    "web": ["sqli", "xss", "auth_bypass"],
    "api": ["insecure_ep", "cmd_inject", "idor"],
    "file": ["path_traversal", "exec_upload"],
    "db": ["sqli", "priv_esc"],
}
BATTLE_DURATION = SLOT_DURATION * len(SLOTS)

state_lock = threading.Lock()
scheduler = BackgroundScheduler(daemon=True)
scheduler.start()

current_slot = 0
battle_started = False
battle_finished = False
battle_start_time = None
slot_start_time = None

teams: Dict[str, Dict[str, Any]] = {}
hp_store: Dict[str, Dict[str, Any]] = {}
overrides: Dict[str, Dict[str, Any]] = {}
events: List[Dict[str, Any]] = []
scores_cache: Dict[str, Any] = {}


def now_ts() -> int:
    return int(time.time())


def json_headers() -> Dict[str, str]:
    return {"Content-Type": "application/json"}


def reset_runtime_state() -> None:
    global current_slot, battle_started, battle_finished, battle_start_time, slot_start_time, hp_store, overrides, events, scores_cache
    current_slot = 0
    battle_started = False
    battle_finished = False
    battle_start_time = None
    slot_start_time = None
    hp_store = {}
    overrides = {}
    events = []
    scores_cache = {}

    for ip in teams:
        hp_store[ip] = {
            "web": MAX_HP["web"],
            "api": MAX_HP["api"],
            "file": MAX_HP["file"],
            "db": MAX_HP["db"],
            "frozen": {},
        }
        overrides[ip] = {"score_override": None, "hp_override": {}}


def team_url(team_ip: str, path: str) -> str:
    return f"http://{team_ip}{path}"


def call_team(team_ip: str, method: str, path: str, payload: Dict[str, Any] = None, retries: int = 1) -> Any:
    payload = payload or {}
    for attempt in range(1, retries + 1):
        try:
            response = requests.request(
                method=method.upper(),
                url=team_url(team_ip, path),
                json=payload,
                headers=json_headers(),
                timeout=5,
            )
            if response.ok:
                return response.json() if response.content else {}
            log.warning("Team call failed %s %s status=%s body=%s", team_ip, path, response.status_code, response.text)
        except Exception as exc:
            log.warning("Team call exception %s %s attempt=%s err=%s", team_ip, path, attempt, exc)
        if attempt < retries:
            time.sleep(2)
    return None


def activate_service_vulns(service_name: str) -> None:
    vulns = VULNS.get(service_name, [])
    for team_ip in list(teams.keys()):
        for vuln in vulns:
            call_team(
                team_ip,
                "POST",
                "/flags/activate",
                {"vuln": vuln, "secret": SECRET},
                retries=3,
            )


def deactivate_service_vulns(service_name: str) -> None:
    vulns = VULNS.get(service_name, [])
    for team_ip in list(teams.keys()):
        for vuln in vulns:
            call_team(
                team_ip,
                "POST",
                "/flags/deactivate",
                {"vuln": vuln, "secret": SECRET},
                retries=3,
            )


def freeze_service(service_name: str) -> None:
    for team_ip, hp_data in hp_store.items():
        hp_data.setdefault("frozen", {})
        hp_data["frozen"][service_name] = hp_data.get(service_name, MAX_HP[service_name])


def unfreeze_current_service(service_name: str) -> None:
    for _, hp_data in hp_store.items():
        hp_data.setdefault("frozen", {})
        hp_data["frozen"].pop(service_name, None)


def schedule_rotation() -> None:
    if scheduler.get_job("rotation"):
        scheduler.remove_job("rotation")
    scheduler.add_job(rotate, "interval", seconds=SLOT_DURATION, id="rotation", replace_existing=True)


def stop_rotation() -> None:
    job = scheduler.get_job("rotation")
    if job:
        scheduler.remove_job("rotation")


def rotate() -> None:
    global current_slot, battle_finished, battle_started, slot_start_time
    with state_lock:
        if not battle_started or battle_finished:
            return

        prev_service = SLOTS[current_slot]
        freeze_service(prev_service)
        deactivate_service_vulns(prev_service)

        if current_slot >= len(SLOTS) - 1:
            battle_finished = True
            battle_started = False
            stop_rotation()
            compute_scores()
            return

        current_slot += 1
        next_service = SLOTS[current_slot]
        unfreeze_current_service(next_service)
        slot_start_time = now_ts()

    activate_service_vulns(next_service)


def append_event(event: Dict[str, Any]) -> None:
    events.append(event)
    if len(events) > 500:
        del events[:-500]


def compute_scores() -> Dict[str, Any]:
    global scores_cache

    with state_lock:
        if not teams:
            scores_cache = {}
            return {}

        attack_success = defaultdict(int)
        attack_attempt = defaultdict(int)
        blocks = defaultdict(int)
        attacks_received = defaultdict(int)
        penalty_points = defaultdict(float)

        for event in events:
            source = event.get("source_team_ip") or "unknown"
            target = event.get("target_team_ip") or "unknown"
            etype = event.get("type", "")

            if etype == "exploit_attempt":
                attack_attempt[source] += 1
                attacks_received[target] += 1
            elif etype == "exploit_success":
                attack_success[source] += 1
                attacks_received[target] += 1
            elif etype == "block":
                blocks[source] += 1

            if etype == "false_positive":
                penalty_points[source] += 10
            elif etype == "self_outage":
                penalty_points[source] += 15
            elif etype == "dos":
                penalty_points[source] += 25

        total_max_hp = sum(MAX_HP.values())
        max_possible = max(1, len(teams) * len(SLOTS))

        result = {}
        for ip, team_meta in teams.items():
            hp_data = hp_store.get(ip, {**MAX_HP, "frozen": {}})
            hp_total = sum(int(hp_data.get(s, MAX_HP[s])) for s in SLOTS)
            hp_score = (hp_total / total_max_hp) * 40

            attack_score = min(25.0, (attack_success[ip] / max_possible) * 25)

            received = attacks_received[ip]
            defense_ratio = 1.0 if received == 0 else (blocks[ip] / max(1, received))
            defense_score = min(20.0, defense_ratio * 20)

            penalty = penalty_points[ip]
            total = hp_score + attack_score + defense_score - penalty

            override_total = overrides.get(ip, {}).get("score_override")
            if override_total is not None:
                total = float(override_total)

            result[ip] = {
                "team_name": team_meta.get("name", ip),
                "hp_score": round(hp_score, 2),
                "attack_score": round(attack_score, 2),
                "defense_score": round(defense_score, 2),
                "penalty": round(-penalty, 2),
                "total": round(total, 2),
                "attacks": attack_success[ip],
                "defenses": blocks[ip],
            }

        scores_cache = result
        return result


def apply_override_hp(team_ip: str, service: str) -> int:
    hp_value = hp_store[team_ip][service]
    override_hp = overrides.get(team_ip, {}).get("hp_override", {}).get(service)
    if override_hp is not None:
        return int(override_hp)
    return int(hp_value)


def check_secret(payload: Dict[str, Any]) -> bool:
    return payload.get("secret") == SECRET


@app.errorhandler(Exception)
def handle_exception(error):
    code = 500
    message = "internal server error"
    if isinstance(error, HTTPException):
        code = error.code or 500
        message = error.description
    log.exception("Request failed: %s", error)
    return jsonify({"ok": False, "error": message}), code


@app.post("/register")
def register():
    payload = request.get_json(silent=True) or {}
    team_name = str(payload.get("team_name", "")).strip()
    ip = str(payload.get("ip", "")).strip()

    if not team_name or not ip:
        return jsonify({"ok": False, "error": "team_name and ip are required"}), 400

    with state_lock:
        teams[ip] = {"name": team_name, "registered_at": now_ts()}
        hp_store[ip] = {
            "web": MAX_HP["web"],
            "api": MAX_HP["api"],
            "file": MAX_HP["file"],
            "db": MAX_HP["db"],
            "frozen": {},
        }
        overrides.setdefault(ip, {"score_override": None, "hp_override": {}})

    return jsonify({"ok": True, "team_name": team_name, "ip": ip})


@app.post("/battle/start")
def battle_start():
    global battle_started, battle_finished, battle_start_time, slot_start_time, current_slot

    with state_lock:
        registered = dict(teams)
        reset_runtime_state()
        teams.update(registered)
        for ip in teams:
            hp_store[ip] = {
                "web": MAX_HP["web"],
                "api": MAX_HP["api"],
                "file": MAX_HP["file"],
                "db": MAX_HP["db"],
                "frozen": {},
            }
            overrides[ip] = {"score_override": None, "hp_override": {}}

        battle_started = True
        battle_finished = False
        current_slot = 0
        battle_start_time = now_ts()
        slot_start_time = battle_start_time

    activate_service_vulns(SLOTS[current_slot])
    schedule_rotation()

    return jsonify({
        "ok": True,
        "started_at": battle_start_time,
        "slot_duration": SLOT_DURATION,
        "teams": len(teams),
    })


@app.post("/battle/stop")
def battle_stop():
    global battle_started, battle_finished
    with state_lock:
        battle_started = False
        battle_finished = True
    stop_rotation()
    final_scores = compute_scores()
    return jsonify({"ok": True, "final_scores": final_scores})


@app.get("/current")
def current():
    with state_lock:
        started = battle_started
        finished = battle_finished
        slot_idx = current_slot
        started_at = battle_start_time
        slot_at = slot_start_time
        teams_count = len(teams)

    now = now_ts()
    elapsed_slot = 0 if not slot_at else max(0, now - slot_at)
    remaining_slot = 0 if finished else max(0, SLOT_DURATION - elapsed_slot)
    battle_elapsed = 0 if not started_at else max(0, now - started_at)
    battle_remaining = 0 if finished else max(0, BATTLE_DURATION - battle_elapsed)

    return jsonify(
        {
            "battle_started": started,
            "battle_finished": finished,
            "active_service": SLOTS[slot_idx],
            "slot": slot_idx + 1,
            "elapsed_seconds": elapsed_slot,
            "remaining_seconds": remaining_slot,
            "battle_elapsed": battle_elapsed,
            "battle_remaining": battle_remaining,
            "teams_registered": teams_count,
        }
    )


@app.get("/teams")
def get_teams():
    with state_lock:
        data = [{"ip": ip, "name": meta.get("name", ip)} for ip, meta in teams.items()]
    return jsonify({"teams": data})


@app.get("/hp")
def get_hp():
    output = {}
    with state_lock:
        for ip in teams:
            output[ip] = {}
            for service in SLOTS:
                current_value = apply_override_hp(ip, service)
                frozen = service in hp_store[ip].get("frozen", {})
                output[ip][service] = {
                    "current": current_value,
                    "max": MAX_HP[service],
                    "frozen": frozen,
                }
    return jsonify(output)


@app.post("/events")
def post_events():
    payload = request.get_json(silent=True) or {}

    event_type = payload.get("type", "exploit_attempt")
    source_team_ip = payload.get("source_team_ip") or payload.get("source_team")
    target_team_ip = payload.get("target_team_ip")
    target_service = payload.get("target_service")
    vuln = payload.get("vuln", "unknown")
    hp_delta = int(payload.get("hp_delta", 0))
    timestamp = int(payload.get("timestamp", now_ts()))

    if not source_team_ip:
        return jsonify({"ok": False, "error": "source_team_ip is required"}), 400

    event = {
        "type": event_type,
        "source_team_ip": source_team_ip,
        "target_team_ip": target_team_ip,
        "target_service": target_service,
        "vuln": vuln,
        "hp_delta": hp_delta,
        "timestamp": timestamp,
    }

    with state_lock:
        append_event(event)

    if event_type == "exploit_success" and target_team_ip and target_service in SLOTS:
        damage_amount = abs(hp_delta) if hp_delta != 0 else 8
        resp = call_team(
            target_team_ip,
            "POST",
            "/damage",
            {"amount": damage_amount, "secret": SECRET},
            retries=3,
        )
        with state_lock:
            if target_team_ip in hp_store:
                if resp and isinstance(resp, dict) and "hp" in resp:
                    hp_store[target_team_ip][target_service] = max(0, min(MAX_HP[target_service], int(resp["hp"])))
                else:
                    hp_store[target_team_ip][target_service] = max(
                        0,
                        hp_store[target_team_ip][target_service] - damage_amount,
                    )

    if event_type == "heal" and target_team_ip and target_service in SLOTS:
        heal_amount = abs(hp_delta) if hp_delta != 0 else 5
        resp = call_team(
            target_team_ip,
            "POST",
            "/heal",
            {"amount": heal_amount, "secret": SECRET},
            retries=2,
        )
        with state_lock:
            if target_team_ip in hp_store:
                if resp and isinstance(resp, dict) and "hp" in resp:
                    hp_store[target_team_ip][target_service] = max(0, min(MAX_HP[target_service], int(resp["hp"])))
                else:
                    hp_store[target_team_ip][target_service] = min(
                        MAX_HP[target_service],
                        hp_store[target_team_ip][target_service] + heal_amount,
                    )

    compute_scores()
    return jsonify({"ok": True})


@app.get("/events")
def get_events():
    with state_lock:
        data = list(events[-100:])
    return jsonify({"events": data})


@app.get("/scores")
def get_scores():
    return jsonify({"scores": compute_scores()})


@app.post("/admin/set_hp")
def admin_set_hp():
    payload = request.get_json(silent=True) or {}
    if not check_secret(payload):
        return jsonify({"ok": False, "error": "unauthorized"}), 401

    team_ip = payload.get("team_ip")
    service = payload.get("service")
    hp_val = payload.get("hp")

    if team_ip not in teams or service not in SLOTS:
        return jsonify({"ok": False, "error": "invalid team or service"}), 400

    hp_int = max(0, min(MAX_HP[service], int(hp_val)))
    with state_lock:
        overrides.setdefault(team_ip, {"score_override": None, "hp_override": {}})
        overrides[team_ip].setdefault("hp_override", {})[service] = hp_int
        hp_store[team_ip][service] = hp_int

    call_team(team_ip, "POST", "/heal", {"amount": MAX_HP[service], "secret": SECRET}, retries=1)
    call_team(team_ip, "POST", "/damage", {"amount": max(0, MAX_HP[service] - hp_int), "secret": SECRET}, retries=1)

    return jsonify({"ok": True})


@app.post("/admin/set_score")
def admin_set_score():
    payload = request.get_json(silent=True) or {}
    if not check_secret(payload):
        return jsonify({"ok": False, "error": "unauthorized"}), 401

    team_ip = payload.get("team_ip")
    score = payload.get("score")
    if team_ip not in teams:
        return jsonify({"ok": False, "error": "invalid team"}), 400

    with state_lock:
        overrides.setdefault(team_ip, {"score_override": None, "hp_override": {}})
        overrides[team_ip]["score_override"] = float(score)

    return jsonify({"ok": True})


@app.post("/admin/rename_team")
def admin_rename_team():
    payload = request.get_json(silent=True) or {}
    if not check_secret(payload):
        return jsonify({"ok": False, "error": "unauthorized"}), 401

    team_ip = payload.get("team_ip")
    name = str(payload.get("name", "")).strip()
    if team_ip not in teams or not name:
        return jsonify({"ok": False, "error": "invalid team or name"}), 400

    with state_lock:
        teams[team_ip]["name"] = name

    return jsonify({"ok": True})


@app.delete("/admin/remove_team")
def admin_remove_team():
    payload = request.get_json(silent=True) or {}
    if not check_secret(payload):
        return jsonify({"ok": False, "error": "unauthorized"}), 401

    team_ip = payload.get("team_ip")
    if team_ip not in teams:
        return jsonify({"ok": False, "error": "team not found"}), 404

    with state_lock:
        teams.pop(team_ip, None)
        hp_store.pop(team_ip, None)
        overrides.pop(team_ip, None)

    return jsonify({"ok": True})


@app.get("/stream")
def stream():
    def event_stream():
        while True:
            computed_scores = compute_scores()
            with state_lock:
                local_teams = []
                for ip, meta in teams.items():
                    hp_map = {
                        service: int(apply_override_hp(ip, service))
                        for service in SLOTS
                    }
                    local_teams.append(
                        {
                            "ip": ip,
                            "name": meta.get("name", ip),
                            "hp": hp_map,
                            "score": computed_scores.get(ip, {}).get("total", 0),
                            "attacks": computed_scores.get(ip, {}).get("attacks", 0),
                            "defenses": computed_scores.get(ip, {}).get("defenses", 0),
                        }
                    )

                payload = {
                    "battle_started": battle_started,
                    "battle_finished": battle_finished,
                    "active_service": SLOTS[current_slot],
                    "remaining_seconds": max(0, SLOT_DURATION - (now_ts() - slot_start_time)) if slot_start_time else SLOT_DURATION,
                    "teams": local_teams,
                    "recent_events": events[-10:],
                    "battle_elapsed": max(0, now_ts() - battle_start_time) if battle_start_time else 0,
                    "battle_remaining": max(0, BATTLE_DURATION - (now_ts() - battle_start_time)) if battle_start_time else BATTLE_DURATION,
                }

            yield f"data: {json.dumps(payload)}\n\n"
            time.sleep(2)

    return Response(event_stream(), mimetype="text/event-stream")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=9000, threaded=True)
