# Scrap Monitoring Visualizer

Scrap Monitoring LiDAR Simulator가 전송하는 Observation version 1 전체 적재면 snapshot을
검증하고 시각화 server에서 렌더링하는 개발용 프로그램이다. Browser에는 고정 사선 직교투영
3D 화면 하나를 제공하고, 선택적으로 현장 camera 시점의 1920 x 1080 MJPEG(Motion JPEG)
stream을 edge device의 V4L2(Video4Linux2) camera로 제공한다.

관찰 기록, 영상 파일과 과거 frame은 저장하지 않는다. Browser 화면과 합성 camera는 같은
Observation을 사용하지만 서로 다른 renderer와 최신 frame 저장소를 사용한다.

## 주요 기능

제품은 다음 2개 OCI(Open Container Initiative) image로 구성된다.

| Image | Platform | 역할 |
| --- | --- | --- |
| `scrap-monitoring-visualizer` | Linux AMD64 | Observation 수신, Browser 화면과 합성 camera 렌더링, HTTP 및 WebSocket 제공 |
| `scrap-monitoring-visualizer-edge-bridge` | Linux ARM64 | MJPEG WebSocket 수신, 검증과 V4L2 virtual camera 기록 |

두 image는 version tag와 source commit tag를 제공하지만 배포에는 Release asset이 기록한
digest 참조를 사용한다. `latest` tag는 제공하지 않는다.

```text
LiDAR Generator -> Visualizer Server -> WebSocket -> Edge Bridge -> V4L2 Camera
                           |
                           +-> Browser Preview
```

## 빠른 시작

Docker Engine과 `curl`이 있는 Linux AMD64 checkout에서 공개 fixture로 첫 화면을 만든다.

```bash
docker build --tag scrap-monitoring-visualizer:quick-start .
docker run --detach --rm \
  --name scrap-monitoring-visualizer-quick-start \
  --publish 127.0.0.1:17000:17000 \
  --publish 127.0.0.1:18000:18000 \
  --env-file .env.example \
  scrap-monitoring-visualizer:quick-start \
  live
until curl --fail --silent http://127.0.0.1:18000/status >/dev/null; do sleep 1; done
bash -c 'exec 3<>/dev/tcp/127.0.0.1/17000; cat contracts/observation/v1/fixtures/observation.v1.jsonl >&3; sleep 2'
curl --fail http://127.0.0.1:18000/status
```

Browser에서 `http://127.0.0.1:18000/`을 열면 고정 사선 3D 화면이 표시된다. 확인 뒤 다음
명령으로 Container를 종료한다.

```bash
docker stop scrap-monitoring-visualizer-quick-start
```

## 설정

### Visualizer

Visualizer 설정은 CLI(Command-Line Interface) 인자, 다음 9개
`SCRAP_MONITORING_VISUALIZER_` 환경 변수, 코드 기본값 순서로 결정한다. Container는 환경
변수로 설정하고 프로그램은 시작할 때 한 번 읽는다. `.env.example`의 image와 publish 주소
2개는 server Compose 전용이며 Visualizer 설정에 포함되지 않는다.

| 환경 변수 | CLI option | 기본값 | 용도 |
| --- | --- | --- | --- |
| `SCRAP_MONITORING_VISUALIZER_TCP_HOST` | `--tcp-host` | 필수 | Observation listen 주소 |
| `SCRAP_MONITORING_VISUALIZER_TCP_PORT` | `--tcp-port` | 필수 | Observation listen port |
| `SCRAP_MONITORING_VISUALIZER_HTTP_HOST` | `--http-host` | 필수 | Preview와 camera service listen 주소 |
| `SCRAP_MONITORING_VISUALIZER_HTTP_PORT` | `--http-port` | 필수 | Preview와 camera service port |
| `SCRAP_MONITORING_VISUALIZER_WIDTH` | `--width` | `1280` | Browser frame 너비 |
| `SCRAP_MONITORING_VISUALIZER_HEIGHT` | `--height` | `720` | Browser frame 높이 |
| `SCRAP_MONITORING_VISUALIZER_CAMERA_ENABLED` | `--camera-enabled` | `false` | 합성 camera 활성화 |
| `SCRAP_MONITORING_VISUALIZER_CAMERA_PROFILE` | `--camera-profile` | 빈 값 | Profile JSON 경로, 빈 값은 내장 profile |
| `SCRAP_MONITORING_VISUALIZER_CAMERA_BACKEND` | `--camera-backend` | profile 값 | `auto`, `osmesa` 또는 `egl` 검증 정책 |

Browser frame 해상도 상한은 3840 x 2160이다. 사용자 profile은 read-only bind mount로
Container에 주입한다.

```bash
docker run \
  --mount type=bind,src=/path/to/camera.v1.json,dst=/run/config/camera.v1.json,readonly \
  --env SCRAP_MONITORING_VISUALIZER_CAMERA_PROFILE=/run/config/camera.v1.json \
  ...
```

`/camera/`, `/camera/v1/status`와 `/camera/v1/stream`은 설정으로 바꾸지 않는 고정 경로다.
Bundled edge bridge는 1920 x 1080, 30 FPS와 최대 4,194,304 byte JPEG만 허용한다. Bridge를
사용할 때 profile의 해당 값은 기본 계약을 유지해야 한다.

### EGL과 GPU

Server image는 기본적으로 OSMesa CPU renderer를 선택한다. EGL(Embedded-System Graphics
Library) GPU renderer는 host의 GPU driver, EGL userspace library와 Container device
전달이 정상인 경우에만 사용한다. NVIDIA GPU는 host의 NVIDIA driver와 NVIDIA Container
Toolkit을 구성하고 `nvidia-smi`와 GPU Container 실행을 먼저 검증해야 한다.

GPU 실행은 `server.env`에서 다음 4개 값을 바꾸고 server setup에 `--gpu`를 전달한다.

```dotenv
SCRAP_MONITORING_VISUALIZER_CAMERA_BACKEND=egl
VTK_DEFAULT_OPENGL_WINDOW=vtkEGLRenderWindow
LIBGL_ALWAYS_SOFTWARE=0
NVIDIA_DRIVER_CAPABILITIES=graphics,utility
```

`auto`는 지원하는 VTK(Visualization Toolkit) render window 중 현재 활성 window를 허용한다.
`osmesa`와 `egl`은 실제 window가 요청한 backend와 다르면 첫 합성 frame 렌더링을 오류로 처리한다. GPU
장애 시 `osmesa`, `vtkOSOpenGLRenderWindow`와 `LIBGL_ALWAYS_SOFTWARE=1`로 되돌린다.

Renderer가 직접 읽는 환경 변수는 다음 2개다. Repository의 `.env.example`은 CPU 기본값을
포함한다.

| 환경 변수 | CPU 기본값 | 용도 |
| --- | --- | --- |
| `VTK_DEFAULT_OPENGL_WINDOW` | `vtkOSOpenGLRenderWindow` | 두 VTK renderer의 off-screen window |
| `LIBGL_ALWAYS_SOFTWARE` | `1` | Mesa software renderer 강제 여부 |

### Edge bridge

Compose 환경 파일은 다음 8개 값을 사용한다.

| 환경 변수 | 기본값 | 용도 |
| --- | --- | --- |
| `SCRAP_SYNTHETIC_CAMERA_BRIDGE_IMAGE` | 필수 | ARM64 image digest 참조 |
| `SCRAP_SYNTHETIC_CAMERA_SERVER_URL` | 필수 | `ws://` camera stream URL |
| `SCRAP_SYNTHETIC_CAMERA_DEVICE` | `/dev/scrap-synthetic-camera` | Container 내부 V4L2 output 경로 |
| `SCRAP_SYNTHETIC_CAMERA_CONNECT_TIMEOUT_MS` | `5000` | TCP 연결과 WebSocket handshake 제한 시간 |
| `SCRAP_SYNTHETIC_CAMERA_IO_TIMEOUT_MS` | `1000` | Stream I/O 제한 시간 |
| `SCRAP_SYNTHETIC_CAMERA_RECONNECT_INITIAL_MS` | `500` | 최초 재연결 대기 시간 |
| `SCRAP_SYNTHETIC_CAMERA_RECONNECT_MAX_MS` | `30000` | 최대 재연결 대기 시간 |
| `SCRAP_SYNTHETIC_CAMERA_VIDEO_GID` | `44` | Host `video` group GID |

Bridge는 최신 frame 1개만 보관하고 절대 deadline을 기준으로 V4L2 output에 30 Hz로
기록한다. 지연된 주기는 건너뛰며 backlog를 만들거나 한 번에 여러 frame을 쓰지 않는다.
`v4l2loopback`은 frame을 추가로 보간하지 않는다.

Bridge는 URL의 credential, query, `wss://`와 계약 이외 경로를 거부한다. Visualizer와
bridge에는 application credential, 인증과 TLS(Transport Layer Security)가 없으므로 Docker
secret을 주입할 항목도 없다. TCP 17000, HTTP 18000과 WebSocket은 외부에 직접 공개하지
않고 접근이 제한된 개발 network에서만 제공한다.

### 서비스 경로와 상태

Visualizer HTTP와 WebSocket 경로는 6개다.

| 경로 | 응답 |
| --- | --- |
| `GET /` | 고정 사선 3D 화면과 상태를 표시하는 웹페이지 |
| `GET /frame.png` | 최신 Browser용 PNG frame |
| `GET /status` | 수신, 렌더링과 합성 camera 상태 JSON |
| `GET /camera/` | 같은 MJPEG stream을 표시하는 합성 camera live 페이지 |
| `GET /camera/v1/status` | 합성 camera 상태 JSON |
| `WebSocket /camera/v1/stream` | Descriptor 1개와 최신 MJPEG binary frame |

Camera 관련 3개 경로는 합성 camera를 활성화한 경우에만 제공한다.

`/status`의 `received_sequence`와 `rendered_sequence`가 같으면 최신 수신 관찰이 Browser
화면에 반영된 상태다. `synthetic_camera`의 `camera_rendered_sequence`, frame 수와 오류는
합성 camera 처리 상태를 나타낸다. 연결이 끊기면 Browser는 마지막 정상 관찰을 disconnected
상태로 표시하고 Visualizer는 같은 TCP port에서 다음 연결을 기다린다.

합성 camera의 초기 WebSocket text message는 다음 JSON이다.

```json
{"type":"camera_stream_descriptor","version":1,"format":"MJPEG","width":1920,"height":1080,"fps":30,"max_frame_bytes":4194304}
```

이후 message는 완전한 JPEG binary 1개다. `/camera/` Browser와 edge bridge는 같은
WebSocket을 사용하며 동시 camera client는 최대 4개다. 보간과 frame 교체 정책의 상세
계약은 [합성 카메라 Live 계약](SYNTHETIC_CAMERA_VIDEO.md)에서 관리한다.

## 개발 및 검증

개발 환경은 Python 3.14.7, uv 0.12.13과 Docker Engine을 사용한다. 전체 검사를 Repository
root에서 실행한다.

```bash
uv sync --locked --all-groups
uv run --frozen rumdl check --no-config --no-cache --disable MD013 .
uv run --frozen python tools/check_repository.py
uv run --frozen ruff format --check src tests tools
uv run --frozen ruff check src tests tools
uv run --frozen mypy
uv run --frozen python -m pytest
uv run --frozen python -m compileall -q src tests tools
cargo install --locked --version 0.9.2 --features cli cargo-about
cargo install --locked --version 0.22.2 cargo-audit
python3 tools/generate_edge_bridge_notices.py --check
cargo audit --file edge-bridge/Cargo.lock
scripts/check-deployment.sh
docker build \
  --file Dockerfile.edge-bridge \
  --target test \
  --tag scrap-monitoring-visualizer-edge-bridge:test \
  .
scripts/check-headless-container.sh
```

CI(Continuous Integration)는 같은 Python 검사, Rust format, Clippy와 test, AMD64 server
Container 검사와 ARM64 edge image build를 `CI` job 하나로 집계한다.

## 배포

Server에는 Linux AMD64, systemd, Docker Engine, Docker Compose plugin, Tailscale, `curl`,
`tar`와 GNU Coreutils가 필요하다. Edge device에는 systemd와 udev를 사용하는 Debian 또는
Ubuntu 계열 Linux ARM64, Docker Engine, Docker Compose plugin, `curl`, `tar`, GNU Coreutils,
현재 kernel header와 root 권한이 필요하다. 90 frame 검사는 edge device에 FFmpeg와
`ffprobe`가 있어야 한다.

최신 Release의 checksum과 배포 bundle을 server와 edge device에서 각각 내려받는다.

```bash
set -euo pipefail
DOWNLOAD_DIRECTORY="$(mktemp -d)"
DEPLOYMENT_DIRECTORY="$(mktemp -d)"
curl --fail --location --silent --show-error \
  --output "$DOWNLOAD_DIRECTORY/deployment.tar.gz" \
  https://github.com/ajin-scrap-monitoring/scrap-monitoring-visualizer/releases/latest/download/deployment.tar.gz
curl --fail --location --silent --show-error \
  --output "$DOWNLOAD_DIRECTORY/SHA256SUMS" \
  https://github.com/ajin-scrap-monitoring/scrap-monitoring-visualizer/releases/latest/download/SHA256SUMS
(
  cd "$DOWNLOAD_DIRECTORY"
  grep ' deployment.tar.gz$' SHA256SUMS | sha256sum --check -
)
tar --extract --gzip \
  --file "$DOWNLOAD_DIRECTORY/deployment.tar.gz" \
  --directory "$DEPLOYMENT_DIRECTORY" \
  --strip-components 1
cd "$DEPLOYMENT_DIRECTORY"
```

두 OCI image는 별도 Public GHCR package에 게시된다. 배포에는 tag가 아니라 다음 Release
asset의 불변 digest 참조를 사용한다.

```bash
VISUALIZER_IMAGE="$(
  curl --fail --location --silent --show-error \
    https://github.com/ajin-scrap-monitoring/scrap-monitoring-visualizer/releases/latest/download/oci-image.txt
)"
EDGE_BRIDGE_IMAGE="$(
  curl --fail --location --silent --show-error \
    https://github.com/ajin-scrap-monitoring/scrap-monitoring-visualizer/releases/latest/download/edge-bridge-oci-image.txt
)"
```

### Visualizer server

환경 파일을 만들고 image 참조, server의 Tailnet IPv4 주소와 합성 camera 설정을 입력한다.
기본 profile은 `SCRAP_MONITORING_VISUALIZER_CAMERA_PROFILE`을 빈 값으로 둔다. 서비스에는
인증과 TLS(Transport Layer Security)가 없으므로 public 또는 전체 interface 주소에
publish하지 않는다.

Server bundle의 Container endpoint는 TCP `0.0.0.0:17000`과 HTTP `0.0.0.0:18000`으로
고정한다. `.env.example`의 4개 endpoint 값을 바꾸지 않는다. Host에는 설정한 Tailnet IPv4
주소로만 두 port를 publish한다. Server bundle은 내장 camera profile을 사용하므로
`SCRAP_MONITORING_VISUALIZER_CAMERA_PROFILE`도 빈 값으로 유지한다. 사용자 profile은 설정
절의 직접 Container mount 경계에서 지원한다.

```bash
cp .env.example server.env
sed --in-place \
  "s|^SCRAP_MONITORING_VISUALIZER_IMAGE=.*|SCRAP_MONITORING_VISUALIZER_IMAGE=$VISUALIZER_IMAGE|" \
  server.env
```

```dotenv
SCRAP_MONITORING_VISUALIZER_PUBLISH_ADDRESS=<server-tailnet-ipv4>
SCRAP_MONITORING_VISUALIZER_CAMERA_ENABLED=true
SCRAP_MONITORING_VISUALIZER_CAMERA_BACKEND=osmesa
```

CPU(Central Processing Unit) renderer로 systemd 서비스를 설치하고 시작한다.

```bash
sudo deploy/server/setup.sh server.env
systemctl status --no-pager scrap-monitoring-visualizer.service
curl --fail "http://<server-tailnet-ipv4>:18000/status"
curl --fail "http://<server-tailnet-ipv4>:18000/camera/v1/status"
```

NVIDIA GPU를 사용하면 설정 절의 EGL 환경 변수를 적용한 뒤 `--gpu`로 설치한다.

```bash
sudo deploy/server/setup.sh server.env --gpu
```

설치된 systemd 서비스는 `tailscale wait`와 설정한 IPv4 검사를 통과한 뒤 foreground Compose를
시작한다. Docker Container에는 restart policy를 주지 않고 systemd가 수명 주기를 관리하므로
Docker가 Tailscale 주소보다 먼저 Container를 복원하지 않는다.

`setup.sh`는 실행 중인 기존 `scrap-monitoring-visualizer` standalone Container가 있으면
restart policy를 제거하고 중지한 뒤 `scrap-monitoring-visualizer-before-systemd-<id>`로
이름을 바꿔 보존한다. 새 digest Container가 정상 상태가 되지 않거나 설치 프로세스가 세션
종료 및 중단 신호를 받으면 기존 설정과 Container를 자동 복원한다. 성공 후 보존 Container는
수동 rollback에 사용할 수 있으며 자동 시작하지 않는다.

Browser에서 `http://<server-tailnet-ipv4>:18000/`을 열면 3D 화면,
`http://<server-tailnet-ipv4>:18000/camera/`를 열면 합성 camera live 화면이 표시된다. 첫
Observation을 받기 전에는 `GET /frame.png`가 HTTP 204를 반환하고 합성 camera는 binary
frame을 전송하지 않는다.

### LiDAR simulator

Observation version 1 producer는 Visualizer TCP endpoint로 전체 적재면 snapshot을 보낸다.
이미 배포된 simulator의 observation host와 port를 server Tailnet 주소와 17000으로 설정한다.
새 `scrap-monitoring-lidar-simulator` checkout은 Rust 1.96.0을 준비하고 별도 terminal에서
다음 명령을 계속 실행한다.

```bash
SIMULATOR_ROOT=/path/to/scrap-monitoring-lidar-simulator
VISUALIZER_ADDRESS=<server-tailnet-ipv4>
mkdir -p /tmp/scrap-lidar-simulator/sockets /tmp/scrap-lidar-simulator/status
cargo run --manifest-path "$SIMULATOR_ROOT/Cargo.toml" --locked -- run \
  --config "$SIMULATOR_ROOT/examples/generator.v2.json" \
  --grpc-socket-dir /tmp/scrap-lidar-simulator/sockets \
  --status-dir /tmp/scrap-lidar-simulator/status \
  --site-id example-site \
  --edge-id example-edge \
  --config-revision example-r1 \
  --deployment-revision example-deployment-r1 \
  --diagnostics-enabled false \
  --observation-host "$VISUALIZER_ADDRESS" \
  --observation-port 17000
```

`GET /status`에서 `received_sequence`가 숫자로 바뀐 뒤 Edge bridge를 검증한다. Simulator의
전체 배포 절차는 해당 Repository의 `docs/deployment.md`가 정본이다.

### Edge bridge

Edge host에서 dedicated virtual camera를 한 번 설정한다.

```bash
sudo deploy/edge/setup-v4l2loopback.sh
```

Script는 `v4l2loopback`을 `/dev/video42`에 구성하고
`/dev/scrap-synthetic-camera` alias를 만든다. 현재 kernel용 module을 즉시 적재할 수 없으면
script가 오류를 반환하며 필요한 재부팅 뒤 setup을 다시 실행해야 한다. Setup은 systemd
oneshot service를 설치하고 활성화해 modules-load 이후 Docker 이전에 MJPG 1920 x 1080,
30 FPS와 `keep_format=1`, `sustain_framerate=0`을 boot마다 복원한다. 실제 camera node는
변경하지 않는다.

Edge 환경 파일에 Release asset의 bridge digest 참조와 server Tailnet 주소를 입력한다.

```bash
cp deploy/edge/.env.example deploy/edge/.env
sed --in-place \
  "s|^SCRAP_SYNTHETIC_CAMERA_BRIDGE_IMAGE=.*|SCRAP_SYNTHETIC_CAMERA_BRIDGE_IMAGE=$EDGE_BRIDGE_IMAGE|" \
  deploy/edge/.env
```

```dotenv
SCRAP_SYNTHETIC_CAMERA_SERVER_URL=ws://<server-tailnet-ipv4>:18000/camera/v1/stream
```

Bridge를 실행하고 virtual camera의 형식, cadence와 decode 가능 여부를 확인한다.

```bash
docker compose \
  --env-file deploy/edge/.env \
  --file deploy/edge/compose.yml \
  up --detach
docker compose \
  --env-file deploy/edge/.env \
  --file deploy/edge/compose.yml \
  logs synthetic-camera-bridge
deploy/edge/check-90-frames.sh /dev/scrap-synthetic-camera
```

Consumer Container는 host의 `/dev/video42` 또는
`/dev/scrap-synthetic-camera`를 Consumer가 기대하는 camera 경로로 mapping한다. 제공 형식은
MJPG FourCC(Four Character Code), 1920 x 1080과 30 FPS(Frames Per Second)다.

Visualizer와 bridge의 시작 순서는 중요하지 않다. Bridge는 server 연결에 실패하거나
연결이 끊기면 500 ms부터 30 s까지 지수 backoff로 재연결한다. 상태 확인이 쉬운 Visualizer를
먼저 시작하는 방식을 권장한다.

## 문서

| 문서 | 역할 |
| --- | --- |
| [프로젝트 명세](docs/project-spec.md) | 초기 제품 범위와 외부 계약의 고정 입력 |
| [합성 카메라 Live 계약](SYNTHETIC_CAMERA_VIDEO.md) | 합성 frame, 보간, WebSocket과 V4L2 계약 |
| [아키텍처](docs/architecture.md) | 현재 설계, 모듈 경계와 내부 처리 정책 |
| [개발 계획](docs/development-plan.md) | 현재 구현과 검증 상태 |
| [의존성](docs/dependencies.md) | 직접 의존성, 라이선스와 검증 환경 |
| [실행 환경](docs/deployment.md) | Image, 릴리스, 자원과 runtime 제약 |
| [계약 출처](contracts/observation/v1/provenance.json) | Observation version 1 고정 사본의 출처와 hash |

## 이용 조건

이 Repository는 코드 검토와 참고를 위해 Public으로 제공하며 프로젝트 소스 코드에 별도
라이선스를 부여하지 않는다.
