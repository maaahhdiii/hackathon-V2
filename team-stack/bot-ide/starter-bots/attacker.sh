#!/usr/bin/env bash
set -u

ORCH="${ORCH:-${ORCHESTRATOR_URL:-http://orchestrator:9000}}"
MY_TARGET="${MY_TARGET:-http://localhost:9100}"
SECRET="${HACKATHON_SECRET:-HACKATHON_SECRET_2025}"

echo "[attacker.sh] started"
while true; do
  vuln=$(printf '%s\n' sql_injection xss csrf rce auth_bypass | shuf -n1)
  service=$(curl -s "$ORCH/current" | grep -Eo '"active_service"\s*:\s*"[^"]+"' | cut -d'"' -f4)
  service="${service:-web}"
  curl -s -X POST "$MY_TARGET/$service/attack" \
    -H 'Content-Type: application/json' \
    -d "{\"vulnerability_type\":\"$vuln\",\"service\":\"$service\",\"secret\":\"$SECRET\"}" >/dev/null
  echo "attack $service/$vuln"
  sleep 3
done
