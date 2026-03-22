#!/usr/bin/env bash
set -u

MY_TARGET="${MY_TARGET:-http://localhost:9100}"

echo "[defender.sh] started"
while true; do
  vuln=$(printf '%s\n' sql_injection xss csrf rce auth_bypass | shuf -n1)
  service=$(printf '%s\n' web api file db | shuf -n1)
  action=$(printf '%s\n' enable disable | shuf -n1)
  curl -s -X POST "$MY_TARGET/$service/defend" \
    -H 'Content-Type: application/json' \
    -d "{\"service\":\"$service\",\"vulnerability_type\":\"$vuln\",\"action\":\"$action\"}" >/dev/null
  echo "defend $service/$vuln/$action"
  sleep 4
done
