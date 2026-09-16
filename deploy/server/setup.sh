#!/usr/bin/env bash
set -euo pipefail

if [[ "${EUID}" -ne 0 ]]; then
  echo "run this setup as root" >&2
  exit 1
fi

if [[ "$#" -lt 1 || "$#" -gt 2 ]]; then
  echo "usage: $0 <server-env-path> [--gpu]" >&2
  exit 2
fi

environment_path="$1"
render_mode=cpu
if [[ "${2:-}" == "--gpu" ]]; then
  render_mode=gpu
elif [[ -n "${2:-}" ]]; then
  echo "unknown option: $2" >&2
  exit 2
fi

if [[ ! -f "$environment_path" ]]; then
  echo "$environment_path is not a regular file" >&2
  exit 1
fi
environment_path="$(realpath -- "$environment_path")"

mapfile -t image_settings < <(
  sed -n 's/^SCRAP_MONITORING_VISUALIZER_IMAGE=//p' "$environment_path"
)
mapfile -t address_settings < <(
  sed -n 's/^SCRAP_MONITORING_VISUALIZER_TAILNET_ADDRESS=//p' "$environment_path"
)
if [[ "${#image_settings[@]}" -ne 1 || \
      ! "${image_settings[0]}" =~ ^ghcr\.io/ajin-scrap-monitoring/scrap-monitoring-visualizer@sha256:[0-9a-f]{64}$ ]]; then
  echo "server environment must contain one release image digest reference" >&2
  exit 1
fi
if [[ "${#address_settings[@]}" -ne 1 || \
      ! "${address_settings[0]}" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  echo "server environment must contain one unquoted Tailnet IPv4 address" >&2
  exit 1
fi
endpoint_settings=(
  SCRAP_MONITORING_VISUALIZER_TCP_HOST=0.0.0.0
  SCRAP_MONITORING_VISUALIZER_TCP_PORT=17000
  SCRAP_MONITORING_VISUALIZER_HTTP_HOST=0.0.0.0
  SCRAP_MONITORING_VISUALIZER_HTTP_PORT=18000
  SCRAP_MONITORING_VISUALIZER_CAMERA_PROFILE=
)
for setting in "${endpoint_settings[@]}"; do
  if [[ "$(grep --count --fixed-strings --line-regexp "$setting" "$environment_path")" -ne 1 ]]; then
    echo "server deployment requires exactly one $setting setting" >&2
    exit 1
  fi
done

for command in docker tailscale systemctl; do
  if [[ "$(command -v "$command")" != "/usr/bin/$command" ]]; then
    echo "/usr/bin/$command is required" >&2
    exit 1
  fi
done

tailscale wait --timeout=120s
tailscale ip --assert="${address_settings[0]}"

script_directory="$(
  unset CDPATH
  cd -- "$(dirname -- "$0")"
  pwd
)"
configuration_directory=/etc/scrap-monitoring-visualizer
installation_directory=/usr/local/lib/scrap-monitoring-visualizer
source_compose=(
  docker compose
  --project-name scrap-monitoring-visualizer-validation
  --env-file "$environment_path"
  --file "$script_directory/compose.yml"
)
if [[ "$render_mode" == "gpu" ]]; then
  source_compose+=(--file "$script_directory/compose.gpu.yml")
fi

SCRAP_MONITORING_VISUALIZER_ENV_FILE="$environment_path" \
  "${source_compose[@]}" config --quiet
SCRAP_MONITORING_VISUALIZER_ENV_FILE="$environment_path" \
  "${source_compose[@]}" pull

managed_targets=(
  "$configuration_directory/server.env"
  "$configuration_directory/render-mode"
  "$installation_directory/compose.yml"
  "$installation_directory/compose.gpu.yml"
  /usr/local/libexec/scrap-monitoring/run-visualizer
  /etc/systemd/system/scrap-monitoring-visualizer.service
)
backup_directory="$(mktemp -d)"
for index in "${!managed_targets[@]}"; do
  target="${managed_targets[$index]}"
  if [[ -e "$target" ]]; then
    cp --archive -- "$target" "$backup_directory/$index"
    : > "$backup_directory/$index.existed"
  fi
done
service_was_active=false
service_was_enabled=false
if systemctl is-active --quiet scrap-monitoring-visualizer.service; then
  service_was_active=true
fi
if systemctl is-enabled --quiet scrap-monitoring-visualizer.service; then
  service_was_enabled=true
fi
legacy_backup_name=""
legacy_restart_argument=""

rollback() {
  result="${1:-$?}"
  trap - ERR HUP INT TERM
  set +e
  systemctl stop scrap-monitoring-visualizer.service
  for index in "${!managed_targets[@]}"; do
    target="${managed_targets[$index]}"
    if [[ -f "$backup_directory/$index.existed" ]]; then
      cp --archive -- "$backup_directory/$index" "$target"
    else
      rm -f -- "$target"
    fi
  done
  systemctl daemon-reload
  if [[ "$service_was_enabled" == true ]]; then
    systemctl enable scrap-monitoring-visualizer.service
  else
    systemctl disable scrap-monitoring-visualizer.service
  fi
  if [[ "$service_was_active" == true ]]; then
    systemctl restart scrap-monitoring-visualizer.service
  fi
  if [[ -n "$legacy_backup_name" ]]; then
    docker rename "$legacy_backup_name" scrap-monitoring-visualizer
    docker update --restart="$legacy_restart_argument" scrap-monitoring-visualizer
    docker start scrap-monitoring-visualizer
  fi
  rm -r -- "$backup_directory"
  exit "$result"
}
trap rollback ERR
trap 'rollback 129' HUP
trap 'rollback 130' INT
trap 'rollback 143' TERM

install -d -m 0755 "$configuration_directory" "$installation_directory"
install -m 0600 "$environment_path" "$configuration_directory/server.env"
printf '%s\n' "$render_mode" > "$configuration_directory/render-mode"
chmod 0644 "$configuration_directory/render-mode"
install -m 0644 "$script_directory/compose.yml" "$installation_directory/compose.yml"
install -m 0644 \
  "$script_directory/compose.gpu.yml" \
  "$installation_directory/compose.gpu.yml"
install -D -m 0755 \
  "$script_directory/run.sh" \
  /usr/local/libexec/scrap-monitoring/run-visualizer
install -m 0644 \
  "$script_directory/scrap-monitoring-visualizer.service" \
  /etc/systemd/system/scrap-monitoring-visualizer.service

/usr/local/libexec/scrap-monitoring/run-visualizer validate

legacy_container_id="$(
  docker ps \
    --quiet \
    --filter name='^/scrap-monitoring-visualizer$'
)"
if [[ -n "$legacy_container_id" ]]; then
  legacy_backup_name="scrap-monitoring-visualizer-before-systemd-${legacy_container_id:0:12}"
  legacy_restart_policy="$(
    docker inspect --format '{{.HostConfig.RestartPolicy.Name}}' "$legacy_container_id"
  )"
  legacy_restart_maximum="$(
    docker inspect --format '{{.HostConfig.RestartPolicy.MaximumRetryCount}}' "$legacy_container_id"
  )"
  legacy_restart_argument="${legacy_restart_policy:-no}"
  if [[ "$legacy_restart_argument" == "on-failure" && \
        "$legacy_restart_maximum" -gt 0 ]]; then
    legacy_restart_argument+="${legacy_restart_argument:+:}$legacy_restart_maximum"
  fi
  docker update --restart=no "$legacy_container_id"
  docker stop --time 15 "$legacy_container_id"
  docker rename "$legacy_container_id" "$legacy_backup_name"
fi

systemctl daemon-reload
systemctl enable scrap-monitoring-visualizer.service
systemctl restart scrap-monitoring-visualizer.service

healthy=false
for _ in $(seq 1 60); do
  container_id="$(
    /usr/local/libexec/scrap-monitoring/run-visualizer container-id
  )"
  if [[ -n "$container_id" && \
        "$(docker inspect --format '{{.State.Health.Status}}' "$container_id")" == "healthy" && \
        "$(docker inspect --format '{{.Config.Image}}' "$container_id")" == "${image_settings[0]}" ]]; then
    healthy=true
    break
  fi
  sleep 1
done
if [[ "$healthy" != true ]]; then
  echo "new Visualizer deployment did not become healthy" >&2
  false
fi

trap - ERR HUP INT TERM
rm -r -- "$backup_directory"
