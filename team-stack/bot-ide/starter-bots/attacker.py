import os
import random
import time

import requests

ORCH = os.getenv("ORCH", os.getenv("ORCHESTRATOR_URL", "http://orchestrator:9000"))
MY_TARGET = os.getenv("MY_TARGET", "http://localhost:9100")
SECRET = os.getenv("HACKATHON_SECRET", "HACKATHON_SECRET_2025")


def get_active_service():
    try:
        r = requests.get(f"{ORCH}/current", timeout=3)
        if r.ok:
            return r.json().get("service", "web")
    except Exception:
        pass
    return "web"


def main():
    print("[attacker.py] started")
    while True:
        service = get_active_service()
        vuln = random.choice(["sql_injection", "xss", "csrf", "rce", "auth_bypass"])
        url = f"{MY_TARGET}/attack"
        payload = {"vulnerability_type": vuln, "secret": SECRET, "service": service}
        try:
            r = requests.post(url, json=payload, timeout=5)
            print(f"attack {service}/{vuln} -> {r.status_code} {r.text[:120]}")
        except Exception as exc:
            print(f"attack error: {exc}")
        time.sleep(3)


if __name__ == "__main__":
    main()
