import os
import re
import threading
import logging
import time

import docker
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
AUTO_STOP_TEAMS_ON_BOOT = os.getenv("AUTO_STOP_TEAMS_ON_BOOT", "true").lower() in {"1", "true", "yes", "on"}
AUTO_STOP_WAIT_SECONDS = int(os.getenv("AUTO_STOP_WAIT_SECONDS", "60"))
COMPOSE_PROJECT_NAME = os.getenv("COMPOSE_PROJECT_NAME", "organizer-stack")
BATTLE_NETWORK = f"{COMPOSE_PROJECT_NAME}_battle-net"
MANAGEMENT_NETWORK = f"{COMPOSE_PROJECT_NAME}_management-net"

_docker_client = None


def team_runtime_info(team_no: int):
    return {
        "team_id": team_no,
        "ip": f"team{team_no}-proxy",
        "proxy_port": 9100 + (team_no - 1),
        "ide_port": 8100 + (team_no - 1),
        "name": f"Team {team_no}",
    }


def get_docker_client():
    global _docker_client
    if _docker_client is None:
        _docker_client = docker.from_env()
    return _docker_client


def team_container_names(team_no: int):
    base = f"team{team_no}"
    return [
        f"{base}-web",
        f"{base}-api",
        f"{base}-file",
        f"{base}-db",
        f"{base}-proxy",
        f"{base}-ide",
    ]


def team_image_name(team_no: int, service: str):
    return f"{COMPOSE_PROJECT_NAME}-team{team_no}-{service}"


def connect_network_with_retry(container, network_name: str, retries: int = 5):
    client = get_docker_client()
    network = client.networks.get(network_name)
    for _ in range(retries):
        try:
            container.reload()
            current_networks = (container.attrs.get("NetworkSettings", {}).get("Networks", {}) or {}).keys()
            if network_name in current_networks:
                return
            network.connect(container)
            return
        except Exception:
            time.sleep(0.3)
    raise RuntimeError(f"failed to connect container {container.name} to network {network_name}")


def create_team_container(team_no: int, service: str):
    client = get_docker_client()
    name = f"team{team_no}-{service}"
    info = team_runtime_info(team_no)

    primary_network = BATTLE_NETWORK

    common_kwargs = {
        "image": team_image_name(team_no, service),
        "name": name,
        "detach": True,
        "network": primary_network,
        "restart_policy": {"Name": "unless-stopped"},
    }

    if service in {"web", "api", "file", "db"}:
        common_kwargs["environment"] = {"HACKATHON_SECRET": SECRET}
    elif service == "proxy":
        common_kwargs["ports"] = {"80/tcp": info["proxy_port"]}
        common_kwargs["environment"] = {"TEAM_NO": str(team_no)}
    elif service == "ide":
        primary_network = MANAGEMENT_NETWORK
        common_kwargs["network"] = primary_network
        common_kwargs["ports"] = {"8080/tcp": info["ide_port"]}
        common_kwargs["environment"] = {
            "TEAM_ID": str(info["team_id"]),
            "TEAM_NAME": info["name"],
            "ORCHESTRATOR_URL": "http://orchestrator:9000",
            "HACKATHON_SECRET": SECRET,
            "MY_PROXY_PORT": str(info["proxy_port"]),
            "SERVER_IP": os.getenv("SERVER_IP", "192.168.1.100"),
        }
        common_kwargs["volumes"] = {
            f"{COMPOSE_PROJECT_NAME}_team{team_no}-code": {"bind": "/app/workspace", "mode": "rw"}
        }

    container = client.containers.run(**common_kwargs)
    if service == "proxy":
        connect_network_with_retry(container, MANAGEMENT_NETWORK)
    return container


def start_team_runtime(team_no: int):
    client = get_docker_client()
    started = []
    missing = []
    services = ["web", "api", "file", "db", "proxy", "ide"]

    for service in services:
        name = f"team{team_no}-{service}"
        try:
            container = client.containers.get(name)
        except docker.errors.NotFound:
            try:
                create_team_container(team_no, service)
                started.append(name)
                continue
            except docker.errors.ImageNotFound:
                missing.append(f"{name} image:{team_image_name(team_no, service)}")
                continue

        container.reload()
        if container.status != "running":
            container.start()
            started.append(name)

    if missing:
        raise RuntimeError(f"missing team containers: {', '.join(missing)}")

    return started


def stop_team_runtime(team_no: int):
    client = get_docker_client()
    for name in team_container_names(team_no):
        try:
            container = client.containers.get(name)
        except docker.errors.NotFound:
            continue

        try:
            container.reload()
            if container.status == "running":
                container.stop(timeout=10)
        except Exception as exc:
            log.warning("Failed to stop container %s: %s", name, exc)


def remove_team_runtime(team_no: int):
    client = get_docker_client()
    for name in team_container_names(team_no):
        try:
            container = client.containers.get(name)
        except docker.errors.NotFound:
            continue

        try:
            container.remove(force=True)
        except Exception as exc:
            log.warning("Failed to remove container %s: %s", name, exc)


def stop_all_team_runtimes():
    for team_no in range(1, MAX_TEAMS + 1):
        try:
            stop_team_runtime(team_no)
        except Exception as exc:
            log.warning("Failed stopping runtime for team %s: %s", team_no, exc)


def remove_all_team_runtimes():
    for team_no in range(1, MAX_TEAMS + 1):
        try:
            remove_team_runtime(team_no)
        except Exception as exc:
            log.warning("Failed removing runtime for team %s: %s", team_no, exc)


def get_running_team_containers():
    client = get_docker_client()
    running = []
    for team_no in range(1, MAX_TEAMS + 1):
        for name in team_container_names(team_no):
            try:
                container = client.containers.get(name)
            except docker.errors.NotFound:
                continue
            container.reload()
            if container.status == "running":
                running.append(name)
    return running


def all_team_containers_exist():
    client = get_docker_client()
    expected = sum(len(team_container_names(team_no)) for team_no in range(1, MAX_TEAMS + 1))
    found = 0
    for team_no in range(1, MAX_TEAMS + 1):
        for name in team_container_names(team_no):
            try:
                client.containers.get(name)
                found += 1
            except docker.errors.NotFound:
                pass
    return found == expected


def bootstrap_runtime_state():
    if not AUTO_STOP_TEAMS_ON_BOOT:
        return

    deadline = time.time() + max(5, AUTO_STOP_WAIT_SECONDS)
    seen_running = False
    while time.time() < deadline:
        try:
            stop_all_team_runtimes()
            remove_all_team_runtimes()
            running = get_running_team_containers()
            if running:
                seen_running = True
            if not running:
                if seen_running:
                    log.info("Stopped all team runtimes at boot (default 0 active teams).")
                else:
                    log.info("No team runtimes active at boot.")
                return
            log.warning("Some team runtimes still running, retrying: %s", ", ".join(running))
            time.sleep(1)
        except Exception as exc:
            log.warning("Runtime bootstrap retry: %s", exc)
            time.sleep(1)

    running = get_running_team_containers()
    if running:
        log.warning("Auto-stop timeout reached; still running: %s", ", ".join(running))


def register_test_teams(count=10, ip_prefix="192.168.1.", ip_start=101, team_prefix="Team", register_mode="proxy_name"):
    results = []
    for idx in range(count):
        team_no = idx + 1
        runtime_error = None

        if register_mode == "proxy_name":
            try:
                start_team_runtime(team_no)
            except Exception as exc:
                runtime_error = str(exc)

        if register_mode == "proxy_name":
            ip = f"team{team_no}-proxy"
        else:
            ip = f"{ip_prefix}{ip_start + idx}"
        payload = {
            "team_name": f"{team_prefix} {team_no}",
            "ip": ip,
        }
        try:
            if runtime_error:
                results.append({"ip": ip, "ok": False, "error": runtime_error})
                continue

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
        if resp.ok:
            match = re.match(r"team(\d+)-proxy$", team_ip)
            if match:
                team_no = int(match.group(1))
                try:
                    stop_team_runtime(team_no)
                    remove_team_runtime(team_no)
                except Exception as exc:
                    log.warning("Failed stopping runtime for team %s: %s", team_no, exc)
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

    try:
        start_team_runtime(team_no)
    except Exception as exc:
        try:
            remove_team_runtime(team_no)
        except Exception:
            pass
        return jsonify({"ok": False, "error": f"failed to start team runtime: {exc}"}), 500

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
    count = int(payload.get("count", 0))
    ip_prefix = str(payload.get("ip_prefix", "192.168.1."))
    ip_start = int(payload.get("ip_start", 101))
    team_prefix = str(payload.get("team_prefix", "Team"))
    register_mode = str(payload.get("register_mode", "proxy_name")).strip().lower()

    if register_mode not in ("proxy_name", "ip"):
        return jsonify({"ok": False, "error": "register_mode must be 'proxy_name' or 'ip'"}), 400

    register_results = []
    ok_count = 0
    if count > 0:
        count = min(50, count)
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
    bootstrap_runtime_state()
    app.run(host="0.0.0.0", port=4000, threaded=True)
