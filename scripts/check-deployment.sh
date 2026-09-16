#!/usr/bin/env bash
set -euo pipefail

shell_scripts=(
  deploy/edge/check-90-frames.sh
  deploy/edge/configure-v4l2loopback.sh
  deploy/edge/setup-v4l2loopback.sh
  deploy/server/run.sh
  deploy/server/setup.sh
  scripts/check-deployment.sh
  scripts/check-headless-container.sh
)

bash -n "${shell_scripts[@]}"
shellcheck "${shell_scripts[@]}"
SCRAP_MONITORING_VISUALIZER_ENV_FILE="$PWD/.env.example" docker compose \
  --env-file .env.example \
  --file deploy/server/compose.yml \
  config --quiet --no-env-resolution --no-path-resolution
server_config="$(
  SCRAP_MONITORING_VISUALIZER_ENV_FILE="$PWD/.env.example" docker compose \
    --env-file .env.example \
    --file deploy/server/compose.yml \
    config --no-env-resolution --no-path-resolution
)"
for port in 17000 18000; do
  grep --quiet --fixed-strings "target: $port" <<< "$server_config"
  grep --quiet --fixed-strings "published: \"$port\"" <<< "$server_config"
done
grep --quiet --fixed-strings \
  'container_name: scrap-monitoring-visualizer' <<< "$server_config"
if grep --quiet --fixed-strings 'host_ip:' <<< "$server_config"; then
  echo "server ports must not restrict the host interface" >&2
  exit 1
fi
SCRAP_MONITORING_VISUALIZER_ENV_FILE="$PWD/.env.example" docker compose \
  --env-file .env.example \
  --file deploy/server/compose.yml \
  --file deploy/server/compose.gpu.yml \
  config --quiet --no-env-resolution --no-path-resolution
docker compose \
  --env-file deploy/edge/.env.example \
  --file deploy/edge/compose.yml \
  config --quiet
edge_config="$(
  docker compose \
    --env-file deploy/edge/.env.example \
    --file deploy/edge/compose.yml \
    config
)"
grep --quiet --fixed-strings \
  'container_name: scrap-monitoring-visualizer-edge-bridge' <<< "$edge_config"
