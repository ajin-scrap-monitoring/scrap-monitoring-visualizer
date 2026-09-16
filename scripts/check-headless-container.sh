#!/usr/bin/env bash
set -euo pipefail

readonly image="${IMAGE_UNDER_TEST:-scrap-monitoring-visualizer:test}"
probe_root="$(mktemp -d)"
readonly probe_root

cleanup() {
  docker run --rm \
    --network none \
    --entrypoint chmod \
    --mount "type=bind,source=${probe_root}/output,target=/output" \
    "${image}" -R a+rwX /output >/dev/null 2>&1 || true
  rm -rf -- "${probe_root}"
}

trap cleanup EXIT

install -d -m 0777 "${probe_root}/output"

if [[ "${SKIP_IMAGE_BUILD:-false}" != "true" ]]; then
  docker build --load --platform linux/amd64 --tag "${image}" .
fi

exposed_ports="$(docker image inspect --format '{{json .Config.ExposedPorts}}' "${image}")"
readonly exposed_ports
test "$(jq -r 'keys | join(" ")' <<<"${exposed_ports}")" = "17000/tcp 18000/tcp"

readonly -a runtime_options=(
  --rm
  --platform linux/amd64
  --network none
  --read-only
  --cap-drop ALL
  --security-opt no-new-privileges
  --pids-limit 128
  --memory 1g
  --cpus 2
  --tmpfs "/tmp:rw,noexec,nosuid,size=64m"
)

docker run "${runtime_options[@]}" \
  --entrypoint sh \
  "${image}" \
  -c 'test ! -e /output && ! command -v ffmpeg >/dev/null'

docker run "${runtime_options[@]}" \
  --mount "type=bind,source=${probe_root}/output,target=/output" \
  --entrypoint python \
  "${image}" \
  -m scrap_monitoring_visualizer.runtime_probe \
  --output /output/probe

cli_help="$(docker run "${runtime_options[@]}" "${image}" --help)"
readonly cli_help
grep -q '{live}' <<<"${cli_help}"
if grep -q 'replay' <<<"${cli_help}"; then
  exit 1
fi

set +e
environment_error="$({
  docker run "${runtime_options[@]}" \
    --env SCRAP_MONITORING_VISUALIZER_TCP_HOST=127.0.0.1 \
    --env SCRAP_MONITORING_VISUALIZER_TCP_PORT=8000 \
    --env SCRAP_MONITORING_VISUALIZER_HTTP_HOST=127.0.0.1 \
    --env SCRAP_MONITORING_VISUALIZER_HTTP_PORT=8000 \
    "${image}" live
} 2>&1)"
environment_status=$?
set -e
readonly environment_error environment_status
test "${environment_status}" -eq 2
grep -q 'TCP and HTTP endpoints must be different' <<<"${environment_error}"

docker run "${runtime_options[@]}" \
  --mount "type=bind,source=${probe_root}/output,target=/output" \
  --entrypoint python \
  "${image}" \
  -m scrap_monitoring_visualizer.dependency_audit \
  --output /output/dependency-inventory.json

docker run "${runtime_options[@]}" \
  --mount "type=bind,source=${probe_root}/output,target=/output" \
  --entrypoint python \
  "${image}" \
  -m scrap_monitoring_visualizer.rendering.probe \
  --output /output/scene

docker run "${runtime_options[@]}" \
  --mount "type=bind,source=${probe_root}/output,target=/output" \
  --entrypoint python \
  "${image}" \
  -m scrap_monitoring_visualizer.synthetic_camera.probe \
  --output /output/camera

docker run "${runtime_options[@]}" \
  --mount "type=bind,source=${probe_root}/output,target=/output" \
  --entrypoint python \
  "${image}" \
  -m scrap_monitoring_visualizer.live_probe \
  --output /output/live

test "$(jq -r '.display_present' "${probe_root}/output/probe/probe.json")" = "false"
test "$(jq -r '.euid' "${probe_root}/output/probe/probe.json")" = "10001"
test "$(jq -r '.gpu_device_present' "${probe_root}/output/probe/probe.json")" = "false"
test "$(jq -r '.render_window' "${probe_root}/output/probe/probe.json")" = "vtkOSOpenGLRenderWindow"
test "$(jq -r '.width' "${probe_root}/output/probe/probe.json")" = "1280"
test "$(jq -r '.height' "${probe_root}/output/probe/probe.json")" = "720"
test -s "${probe_root}/output/probe/frame.png"
test "$(jq -r '.display_present' "${probe_root}/output/scene/scene.json")" = "false"
test "$(jq -r '.euid' "${probe_root}/output/scene/scene.json")" = "10001"
test "$(jq -r '.render_window' "${probe_root}/output/scene/scene.json")" = "vtkOSOpenGLRenderWindow"
test "$(jq -r '.parallel_projection' "${probe_root}/output/scene/scene.json")" = "true"
test "$(jq -r '.width' "${probe_root}/output/scene/scene.json")" = "1280"
test "$(jq -r '.height' "${probe_root}/output/scene/scene.json")" = "720"
test "$(jq -r '.surface_faces > 0' "${probe_root}/output/scene/scene.json")" = "true"
test "$(jq -r '.volume_side_faces > 0' "${probe_root}/output/scene/scene.json")" = "true"
test "$(jq -c '.height_range_m' "${probe_root}/output/scene/scene.json")" = '[0.0,1.0]'
test -s "${probe_root}/output/scene/scene.png"
test "$(jq -r '.format' "${probe_root}/output/camera/camera.json")" = "MJPEG"
test "$(jq -r '.width' "${probe_root}/output/camera/camera.json")" = "640"
test "$(jq -r '.height' "${probe_root}/output/camera/camera.json")" = "360"
test "$(jq -r '.perspective' "${probe_root}/output/camera/camera.json")" = "true"
test "$(jq -r '.render_backend' "${probe_root}/output/camera/camera.json")" = "vtkOSOpenGLRenderWindow"
test "$(jq -r '.frame_bytes > 0 and .frame_bytes <= 4194304' "${probe_root}/output/camera/camera.json")" = "true"
test -s "${probe_root}/output/camera/camera.jpg"
test "$(jq -r '.frame_before_observation' "${probe_root}/output/live/live.json")" = "204"
test "$(jq -r '.tcp_response_bytes' "${probe_root}/output/live/live.json")" = "0"
test "$(jq -r '.frame_status' "${probe_root}/output/live/live.json")" = "200"
test "$(jq -r '.status_code' "${probe_root}/output/live/live.json")" = "200"
test "$(jq -r '.root_status' "${probe_root}/output/live/live.json")" = "200"
test "$(jq -r '.root_has_preview' "${probe_root}/output/live/live.json")" = "true"
test "$(jq -r '.root_has_camera' "${probe_root}/output/live/live.json")" = "true"
test "$(jq -r '.received_sequence' "${probe_root}/output/live/live.json")" = "1"
test "$(jq -r '.rendered_sequence' "${probe_root}/output/live/live.json")" = "1"
test "$(jq -r '.recording_present' "${probe_root}/output/live/live.json")" = "false"
test -s "${probe_root}/output/live/live.png"
test "$(jq -r '.machine' "${probe_root}/output/dependency-inventory.json")" = "x86_64"
test "$(jq -r '.python_distributions | length > 0' "${probe_root}/output/dependency-inventory.json")" = "true"
test "$(jq -r '.debian_packages | length > 0' "${probe_root}/output/dependency-inventory.json")" = "true"

benchmark_json="$(
  docker run "${runtime_options[@]}" \
    --entrypoint python \
    "${image}" \
    -m scrap_monitoring_visualizer.runtime_probe \
    --output /tmp/benchmark \
    --grid-x 512 \
    --grid-y 512
)"
readonly benchmark_json
test "$(jq -r '.grid_points' <<<"${benchmark_json}")" = "262144"
printf '%s\n' "${benchmark_json}"
