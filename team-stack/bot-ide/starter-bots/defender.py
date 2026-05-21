"""
Empty starter defender bot — intentionally does nothing.
"""

def main():
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
    "web": ["sqli", "xss", "auth_bypass"],
    "api": ["insecure_ep", "cmd_inject", "idor"],
    "file": ["path_traversal", "exec_upload"],
    "db": ["sqli", "priv_esc"],
}


def get_health(service):
    r = requests.get(f"{MY_TARGET}/{service}/health", timeout=5)
    return r.status_code, r.json() if r.ok else {"raw": r.text}


def deactivate(service, vuln):
    r = requests.post(
        f"{MY_TARGET}/{service}/flags/deactivate",
        json={"secret": HACKATHON_SECRET, "vuln": vuln},
        timeout=5,
    )
    return r.status_code, r.text[:160]


def heal(service, amount=5):
    r = requests.post(
        f"{MY_TARGET}/{service}/heal",
        json={"secret": HACKATHON_SECRET, "amount": amount},
        timeout=5,
    )
    return r.status_code, r.text[:160]


def main():
    print("[defender.py] started")
    while True:
        for service, vulns in SERVICE_VULNS.items():
            try:
                status, data = get_health(service)
                print(f"health {service} -> {status} {data}")
                for vuln in vulns:
                    print(f"deactivate {service}/{vuln} ->", deactivate(service, vuln))
                hp = int(data.get("hp", 0) or 0)
                max_hp = int(data.get("max_hp", hp) or hp)
                if hp < max_hp:
                    print(f"heal {service} ->", heal(service, 5))
            except Exception as exc:
                print(f"defend error on {service}: {exc}")
        time.sleep(4)


if __name__ == "__main__":
    main()
