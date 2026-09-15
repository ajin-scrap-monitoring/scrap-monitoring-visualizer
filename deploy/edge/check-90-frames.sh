#!/usr/bin/env bash
set -euo pipefail

device="${1:-/dev/scrap-synthetic-camera}"
if [[ ! -c "$device" ]]; then
  echo "$device is not a character device" >&2
  exit 1
fi

for command in ffmpeg ffprobe v4l2-ctl; do
  if ! command -v "$command" >/dev/null 2>&1; then
    echo "$command is required" >&2
    exit 1
  fi
done

temporary_directory="$(mktemp -d)"
trap 'rm -r -- "$temporary_directory"' EXIT
capture="$temporary_directory/capture.mkv"

v4l2-ctl --device "$device" --get-fmt-video
started_at_nanoseconds="$(date +%s%N)"
timeout 15s ffmpeg \
  -hide_banner \
  -loglevel error \
  -f v4l2 \
  -input_format mjpeg \
  -video_size 1920x1080 \
  -framerate 30 \
  -i "$device" \
  -frames:v 90 \
  -c:v copy \
  "$capture"
finished_at_nanoseconds="$(date +%s%N)"
elapsed_milliseconds="$((
  (finished_at_nanoseconds - started_at_nanoseconds) / 1000000
))"
if [[ "$elapsed_milliseconds" -lt 2500 || "$elapsed_milliseconds" -gt 5000 ]]; then
  echo "90 frames took an unexpected $elapsed_milliseconds ms" >&2
  exit 1
fi

stream_probe="$(
  ffprobe \
    -v error \
    -select_streams v:0 \
    -count_packets \
    -show_entries stream=codec_name,width,height,nb_read_packets \
    -of default=noprint_wrappers=1 \
    "$capture"
)"
grep -qx 'codec_name=mjpeg' <<<"$stream_probe"
grep -qx 'width=1920' <<<"$stream_probe"
grep -qx 'height=1080' <<<"$stream_probe"
grep -qx 'nb_read_packets=90' <<<"$stream_probe"

maximum_packet_bytes="$(
  ffprobe \
    -v error \
    -select_streams v:0 \
    -show_entries packet=size \
    -of csv=p=0 \
    "$capture" \
    | awk 'BEGIN { maximum = 0 } { if ($1 > maximum) maximum = $1 } END { print maximum }'
)"
if [[ "$maximum_packet_bytes" -le 0 || "$maximum_packet_bytes" -gt 4194304 ]]; then
  echo "invalid maximum packet size: $maximum_packet_bytes" >&2
  exit 1
fi

ffmpeg -hide_banner -loglevel error -i "$capture" -frames:v 90 -f null -
echo "OK: captured 90 MJPEG 1920x1080 frames in $elapsed_milliseconds ms; max packet $maximum_packet_bytes bytes"
