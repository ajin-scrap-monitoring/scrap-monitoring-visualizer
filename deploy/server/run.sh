#!/usr/bin/env bash
set -euo pipefail

configuration_directory=/etc/scrap-monitoring-visualizer
installation_directory=/usr/local/lib/scrap-monitoring-visualizer
compose_files=(--file "$installation_directory/compose.yml")

if [[ "$(< "$configuration_directory/render-mode")" == "gpu" ]]; then
  compose_files+=(--file "$installation_directory/compose.gpu.yml")
fi

compose=(
  /usr/bin/docker compose
  --project-name scrap-monitoring-visualizer
  --env-file "$configuration_directory/server.env"
  "${compose_files[@]}"
)

case "${1:-}" in
  start)
    exec "${compose[@]}" up --no-color --remove-orphans
    ;;
  stop)
    exec "${compose[@]}" down --timeout 15
    ;;
  validate)
    "${compose[@]}" config --quiet
    ;;
  pull)
    "${compose[@]}" pull
    ;;
  container-id)
    "${compose[@]}" ps --quiet visualizer
    ;;
  *)
    echo "usage: $0 {start|stop|validate|pull|container-id}" >&2
    exit 2
    ;;
esac
