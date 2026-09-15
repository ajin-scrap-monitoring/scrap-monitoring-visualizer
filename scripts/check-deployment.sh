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
docker compose \
  --env-file .env.example \
  --file deploy/server/compose.yml \
  config --quiet --no-env-resolution --no-path-resolution
docker compose \
  --env-file .env.example \
  --file deploy/server/compose.yml \
  --file deploy/server/compose.gpu.yml \
  config --quiet --no-env-resolution --no-path-resolution
docker compose \
  --env-file deploy/edge/.env.example \
  --file deploy/edge/compose.yml \
  config --quiet
