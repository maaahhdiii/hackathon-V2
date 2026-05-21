done
#!/usr/bin/env bash
set -u

MY_TARGET="${MY_TARGET:-http://localhost:9100}"
SECRET="${HACKATHON_SECRET:-HACKATHON_SECRET_2025}"

echo "[defender.sh] started"
while true; do
  for service in web api file db; do
    case "$service" in
      web) vulns="sqli xss auth_bypass" ;;
      api) vulns="insecure_ep cmd_inject idor" ;;
      file) vulns="path_traversal exec_upload" ;;
      db) vulns="sqli priv_esc" ;;
    esac
    for vuln in $vulns; do
      curl -s -X POST "$MY_TARGET/$service/flags/deactivate" \
        -H 'Content-Type: application/json' \
        -d "{\"secret\":\"$SECRET\",\"vuln\":\"$vuln\"}" >/dev/null
      echo "deactivate $service/$vuln"
    done
    curl -s -X POST "$MY_TARGET/$service/heal" \
      -H 'Content-Type: application/json' \
      -d "{\"secret\":\"$SECRET\",\"amount\":5}" >/dev/null
    echo "heal $service"
  done
  sleep 4
done
