#!/usr/bin/env bash
set -euo pipefail

app_service="${DOUYIN_SERVICE_NAME:-douyin-downloader-refactor.service}"
tunnel_service="${DOUYIN_TUNNEL_SERVICE_NAME:-}"
health_url="${DOUYIN_HEALTH_URL:-http://127.0.0.1:9000/health/live}"

restart_service() {
  local service="$1"
  echo "Restarting unhealthy service: $service"
  systemctl restart "$service"
}

if ! systemctl is-active --quiet "$app_service"; then
  restart_service "$app_service"
fi

healthy=false
for _ in {1..10}; do
  if curl --fail --silent --show-error --max-time 10 "$health_url" 2>/dev/null | grep -q '"status":"ok"'; then
    healthy=true
    break
  fi
  sleep 1
done
if [[ "$healthy" != "true" ]]; then
  restart_service "$app_service"
fi

if [[ -n "$tunnel_service" ]] && ! systemctl is-active --quiet "$tunnel_service"; then
  restart_service "$tunnel_service"
fi
