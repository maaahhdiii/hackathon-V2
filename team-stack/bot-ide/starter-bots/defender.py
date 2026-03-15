import os
import random
import time

import requests

MY_TARGET = os.getenv("MY_TARGET", "http://localhost:9100")


def main():
    print("[defender.py] started")
    while True:
        service = random.choice(["web", "dns", "mail"])
        action = random.choice(["enable", "disable"])
        vuln = random.choice(["sql_injection", "xss", "csrf", "rce", "auth_bypass"])
        payload = {"service": service, "vulnerability_type": vuln, "action": action}
        try:
            r = requests.post(f"{MY_TARGET}/defend", json=payload, timeout=5)
            print(f"defend {service}/{vuln}/{action} -> {r.status_code} {r.text[:120]}")
        except Exception as exc:
            print(f"defend error: {exc}")
        time.sleep(4)


if __name__ == "__main__":
    main()
