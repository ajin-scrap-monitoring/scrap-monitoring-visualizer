# 실행 환경

## 배포 단위

배포 단위는 다음 2개 OCI(Open Container Initiative) image다.

| Image | Platform | Entrypoint | Network 및 device |
| --- | --- | --- | --- |
| Visualizer | Linux AMD64 | `scrap-monitoring-visualizer` | TCP 17000, HTTP와 WebSocket 18000 |
| Edge bridge | Linux ARM64 | `scrap-synthetic-camera-bridge` | Outbound WebSocket, V4L2 `/dev/video42` |

Visualizer image는 Observation receiver, Browser renderer, 선택적 synthetic renderer와
HTTP 및 WebSocket service를 포함한다. Edge bridge image는 WebSocket frame을 검증해
V4L2(Video4Linux2) output에 기록하며 renderer와 Python runtime을 포함하지 않는다.

두 Container는 UID(User Identifier)와 GID(Group Identifier) 10001인 비root process로
실행한다. Root filesystem은 read-only이며 운영 Observation과 frame을 volume이나 image
layer에 저장하지 않는다. 로그는 표준 출력과 표준 오류로만 기록하고 Docker log rotation을
설정한다.

환경 변수 주입, image digest 조회, server 실행과 edge Compose 절차는
[README](../README.md)의 배포 절을 따른다.

## Visualizer runtime

Visualizer는 `/tmp`에만 제한된 tmpfs를 사용한다. 기본 image 환경은
`vtkOSOpenGLRenderWindow`, `LIBGL_ALWAYS_SOFTWARE=1`, `PYVISTA_OFF_SCREEN=true`와 빈
`DISPLAY`를 사용하는 OSMesa CPU renderer다. Browser camera와 synthetic camera는 같은 VTK
render window 설정을 사용한다.

Synthetic camera가 비활성화되면 주 process와 Browser render process만 실행한다.
활성화되면 별도 synthetic render process, 최신 JPEG 저장소와 WebSocket endpoint를
추가한다. Renderer process는 각각 처리 중 1개와 pending 1개만 유지한다.

CPU mode는 GPU device와 Container GPU runtime이 필요하지 않다. EGL(Embedded-System
Graphics Library) mode의 선행 조건은 다음 5개다.

1. Host GPU와 호환되는 kernel driver
2. Container에 GPU device와 vendor EGL library를 제공하는 runtime
3. `VTK_DEFAULT_OPENGL_WINDOW=vtkEGLRenderWindow`
4. `LIBGL_ALWAYS_SOFTWARE=0`과 camera backend `egl`
5. NVIDIA runtime의 `graphics,utility` driver capability

NVIDIA GPU는 NVIDIA driver와 NVIDIA Container Toolkit을 host에 설치하고 `--gpus all` 및
`NVIDIA_DRIVER_CAPABILITIES=graphics,utility`로 device와 EGL library를 전달한다. `nvidia-smi`가
host와 test Container에서 모두 성공한 뒤 EGL mode를 사용한다. VTK가
`vtkEGLRenderWindow`를 만들지 못하면 camera 상태에 오류를 기록하며 CPU mode로 자동
fallback하지 않는다.

Server의 지속 배포 파일은 다음 5개다.

| 설정 파일 | 역할 |
| --- | --- |
| `deploy/server/compose.yml` | 비root Container, 자원과 host port binding |
| `deploy/server/compose.gpu.yml` | NVIDIA GPU device 요청 |
| `deploy/server/run.sh` | 선택한 Compose 구성의 foreground 수명 주기 |
| `deploy/server/scrap-monitoring-visualizer.service` | Tailscale 준비 이후 실행과 재시작 |
| `deploy/server/setup.sh` | 환경 및 실행 파일 설치, image pull과 service 활성화 |

Server Container에는 Docker restart policy를 설정하지 않는다. Systemd는 `tailscale wait`와
설정한 Tailnet IPv4 검사를 통과한 뒤 foreground Compose process를 실행하고 오류 종료를
재시작한다. Docker가 boot 중 Tailnet 주소 생성 전에 Container를 복원하지 않는다.
Docker daemon이 재시작되어 Compose process가 종료되어도 systemd의 재시작 loop가 daemon
복귀 뒤 Container를 다시 시작한다.
Container endpoint는 TCP `0.0.0.0:17000`과 HTTP `0.0.0.0:18000`으로 고정한다. Compose는
host IP를 지정하지 않고 host의 17000과 18000에 publish한다. 원격 loopback의 HTTP port는
SSH local port forwarding 대상이다.

## Edge runtime

Edge bridge Container는 Docker bridge network, read-only root, capability 없음, process
32개, memory 64 MiB와 CPU 0.25개 제한을 사용한다. Host `/dev/video42`만 Container의 설정된
synthetic camera 경로로 전달하고 host `video` group GID를 supplemental group으로 추가한다.

Edge host의 cgroup v2 controller 목록에는 `memory`가 있어야 하며 Docker의 `MemoryLimit`과
`SwapLimit`은 모두 `true`여야 한다. Memory controller가 보이지 않으면 Raspberry Pi의
`/boot/firmware/cmdline.txt`에서 `cgroup_disable=memory`를 제거하고 기존 한 줄에
`cgroup_enable=memory`를 추가한 뒤 재부팅한다. 이 설정을 바꾼 뒤에는 Compose가 bridge
Container를 다시 생성해야 64 MiB memory 제한을 적용한다.

Edge host는 Container 실행 전에 다음 5개 지속 설정을 한 번 적용한다.

| 설정 파일 | 역할 |
| --- | --- |
| `deploy/edge/v4l2loopback.conf` | Device 42, label, capability와 buffer module option |
| `deploy/edge/scrap-synthetic-camera.modules-load.conf` | Boot 시 module 적재 |
| `deploy/edge/99-scrap-synthetic-camera.rules` | Group, mode와 semantic alias 생성 |
| `deploy/edge/configure-v4l2loopback.sh` | MJPG, 해상도, FPS와 buffer control 설정 |
| `deploy/edge/scrap-synthetic-camera-configure.service` | Modules-load 이후, Docker 이전 설정 복원 |

`deploy/edge/setup-v4l2loopback.sh`는 현재 kernel header, `v4l2loopback` DKMS(Dynamic Kernel
Module Support)와 V4L2 도구를 설치하고 MJPG 1920 x 1080, 30 FPS,
`keep_format=1`, `sustain_framerate=0`을 설정한다. Script는 systemd oneshot을 설치하고
enable한 뒤 즉시 실행하며 이 service가 같은 설정을 boot마다 복원한다. `/dev/video42`가
이미 다른 장치에 속하면 설정을 성공으로 처리하지 않는다.

Bridge는 application credential을 사용하지 않는다. `ws://` endpoint에는 인증과
TLS(Transport Layer Security)가 없으므로 server와 edge 사이의 network 접근 제어가
보안 경계다.

## 로컬 image 검증

AMD64 Visualizer image를 빌드한다.

```bash
docker build \
  --platform linux/amd64 \
  --tag scrap-monitoring-visualizer:test \
  .
```

제한된 Container에서 Browser frame과 synthetic camera JPEG를 실제로 생성한다.

```bash
scripts/check-headless-container.sh
```

검사는 network, Linux capability와 GPU device를 제공하지 않는다. 비root와 read-only root,
OSMesa render window, 직교 PNG, 원근 JPEG, TCP 무응답 계약, HTTP 상태와 의존성 notice를
확인한다.

Rust source와 release binary를 Linux builder에서 검사한다.

```bash
cargo install --locked --version 0.9.2 --features cli cargo-about
cargo install --locked --version 0.22.2 cargo-audit
python3 tools/generate_edge_bridge_notices.py --check
cargo audit --file edge-bridge/Cargo.lock
docker build \
  --file edge-bridge/Dockerfile \
  --target test \
  --tag scrap-monitoring-visualizer-edge-bridge:test \
  .
```

CI(Continuous Integration)는 QEMU와 Buildx로 Linux ARM64 runtime image까지 빌드한다. 실제
V4L2 device의 90 frame cadence, decode, 연속 sequence와 monotonic EOF timestamp 검증은
ARM64 edge host에서 Release digest image를 실행한 뒤 `deploy/edge/check-90-frames.sh`로
수행한다.

## 릴리스 정책

Release workflow는 `vMAJOR.MINOR.PATCH` tag가 원격 `main`에 포함된 동일 version commit을
가리킬 때만 실행한다. Python package, Python module과 Rust package version은 모두 tag와
같아야 한다.

Workflow가 게시하고 검증하는 산출물은 다음 9개 종류다.

| 산출물 | 검증 |
| --- | --- |
| AMD64 Visualizer image | Platform, OCI label, headless 실행과 공개 범위 |
| ARM64 Edge Bridge image | Platform, OCI label과 공개 범위 |
| Image tag | Version 및 `sha-<commit>` tag의 동일 manifest digest |
| Supply chain | 두 image의 SPDX(Software Package Data Exchange) SBOM과 SLSA provenance, Edge crate 및 Rust 고지 |
| Python package | Wheel과 source archive |
| 배포 파일 | Server systemd 및 Compose와 Edge setup, Compose 및 90 frame 검사 bundle |
| Image 참조 | `oci-image.txt`, `edge-bridge-oci-image.txt`의 digest 참조 |
| Release metadata | Source commit, version, 두 image와 platform |
| Integrity | 모든 Release asset의 SHA-256 checksum |

Workflow는 기존 tag가 있으면 두 image의 version 및 commit tag가 같은 digest인지 확인한다.
한 tag만 남은 중단 상태는 기존 image의 platform, label, SBOM과 provenance를 검증한 뒤 누락
tag를 같은 digest로 복구한다. 두 tag의 digest가 다르면 실패한다. 새 image와 asset은 draft
Release에 모은 뒤 모든 검사를 통과한 경우에만 Public Release로 전환한다. `latest` image
tag는 게시하지 않는다.

신규 GHCR package는 최초 게시 시 Private이다. 첫 Candidate 실행이 Edge Bridge package를
만든 뒤 조직 owner가 GitHub의 해당 Package settings에서 visibility를 Public으로 바꾸고
Candidate를 다시 실행한다. 두 package의 Public API 확인과 Candidate 성공 전에는 Release
tag를 생성하지 않는다.

Release 직전에는 CI와 CodeQL 결과, main ancestry, version 일치, 두 platform, 공개 GHCR
(GitHub Container Registry), SBOM, provenance와 draft publication 순서를 다시 검토한다.

## 자원 기준

정적 입력과 Browser renderer 상한은 다음 5개다.

| 항목 | 기준 |
| --- | --- |
| Browser 기본 해상도 | 1280 x 720 |
| Browser 최대 해상도 | 3840 x 2160 |
| 최대 격자 node | 262,144 |
| 최대 surface triangle | 1,048,576 |
| 최대 clipping edge 검사 | 16,777,216 |

경계 polygon은 최대 vertex 1,024개를 허용한다. 수치 상한의 정본은
[`limits.py`](../src/scrap_monitoring_visualizer/limits.py)다. Synthetic camera profile의
frame, FPS와 byte 상한은 [합성 카메라 Live 계약](../SYNTHETIC_CAMERA_VIDEO.md)에서
관리한다.

2026-09-13 Linux AMD64 host에서 Docker Engine 29.5.2와 OSMesa로 측정한 Browser renderer
기준은 다음과 같다.

| 입력 | Frame | Rendering | 최대 RSS |
| --- | --- | --- | --- |
| 격자 node 825개 | 1280 x 720, 1 frame | 0.527 s | 410.004 MiB |
| 격자 node 262,144개 | 1280 x 720, 1 frame | 0.974 s | 535.914 MiB |

이 값은 성능 보장이 아니라 Browser renderer의 회귀 비교 기준이다. Synthetic camera를
활성화한 server는 두 VTK process를 위해 memory 3 GiB와 CPU 2개를 초기 배포 예산으로
사용한다. 1920 x 1080의 고유 frame render 처리량과 EGL 자원 사용은 P8 실제 장비 검증에서
측정하며 검증 전에는 30개의 고유 frame을 매초 생성한다고 가정하지 않는다.
