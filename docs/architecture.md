# 구현 아키텍처

## 문서 역할

이 문서는 채택한 구현 설계의 정본이다. 초기 제품 요구사항은
[프로젝트 명세](project-spec.md), 현재 구현과 검증 상태는
[개발 계획](development-plan.md), 합성 camera의 외부 계약은
[합성 카메라 Live 계약](../SYNTHETIC_CAMERA_VIDEO.md)에서 관리한다.

현재 제품은 Browser용 고정 사선 3D 화면과 edge device용 원근 합성 camera stream을
실시간으로 제공한다. 관찰 기록, replay, 영상 파일, 상면 화면, depth map과 class mask는
제공하지 않는다.

## 소스 경계

Python server는 `src/scrap_monitoring_visualizer/` 아래의 다음 9개 경계로 구성한다.

| 경계 | 책임 |
| --- | --- |
| `cli.py` | 환경 변수, CLI(Command-Line Interface) 인자와 실행 수명 관리 |
| `contracts/` | 원본 레코드 해석, schema 및 의미 검증, 내부 불변 자료형 |
| `receiver/` | TCP(Transmission Control Protocol) 연결과 LF(Line Feed) 레코드 조립 |
| `state/` | 실행 식별, sequence 판정, 연결 상태와 최신 Observation |
| `geometry/` | 경계 삼각분할, 표면 clipping과 결정론적 mesh |
| `rendering/` | Browser용 직교투영 장면과 PNG frame |
| `preview/` | HTTP(Hypertext Transfer Protocol) 상태, PNG와 Browser 화면 |
| `synthetic_camera/` | Profile, 보간, 원근 장면, camera page, JPEG와 WebSocket stream |
| `dependency_audit.py` | Server image의 version과 license notice inventory |

`contracts/` 자료형을 geometry와 두 renderer가 공유한다. `geometry/`는 수치 mesh를 반환하고
VTK(Visualization Toolkit)를 호출하지 않는다. 네트워크, Browser renderer와 합성 camera
renderer는 각각 `receiver/`, `rendering/`과 `synthetic_camera/`에 격리한다.

Rust edge bridge는 `edge-bridge/src/` 아래의 다음 7개 경계로 구성한다.

| 경계 | 책임 |
| --- | --- |
| `main.rs` | 환경 설정, signal과 process 종료 code |
| `config.rs` | URL, device, timeout과 재연결 구간 검증 |
| `bridge.rs` | WebSocket session, message 순서와 V4L2 기록 |
| `descriptor.rs` | Camera descriptor version 1 검증 |
| `jpeg.rs` | JPEG marker, SOF 크기와 byte 상한 검증 |
| `device.rs` | V4L2 capability, output format과 frame write |
| `backoff.rs` | Bounded 지수 재연결 대기 |

Rust bridge는 JPEG를 decode하거나 encode하지 않는다. Server의 Observation 계약과 Python
package를 의존하지 않고 camera stream 계약만 공유한다.

Parser는 package 내부의 Observation version 1 schema를 기본 입력으로 사용한다. 저장소
검사는 package schema가 `contracts/observation/v1/`의 고정 사본과 byte 단위로 같은지
확인하고 wheel 검사는 두 schema가 배포 산출물에 포함되는지 확인한다.

## 실행 설정

Server 설정은 CLI 인자, `SCRAP_MONITORING_VISUALIZER_` 환경 변수, 코드 기본값 순서로
결정한다. 실행 mode는 `live` 하나다. Environment와 CLI 값은 같은 `LiveConfig`와 camera
profile 검증을 거치며 process 시작 뒤에는 다시 읽지 않는다.

Edge bridge는 `SCRAP_SYNTHETIC_CAMERA_` 환경 변수만 읽는다. Server URL, V4L2 device,
연결 및 I/O timeout과 재연결 구간을 시작 시 검증한다. 환경 변수 목록과 주입 절차의 정본은
[README](../README.md)다.

## 기술 선택

구현 기술은 다음 7개 묶음이다. 고정 version과 license는
[의존성](dependencies.md)에서 관리한다.

| 기술 | 채택 목적 | 공식 출처 |
| --- | --- | --- |
| Python과 uv | Server 조립, 계약 검증과 의존성 고정 | [Python](https://www.python.org/), [uv](https://docs.astral.sh/uv/) |
| jsonschema | 고정 JSON(JavaScript Object Notation) Schema 검증 | [jsonschema](https://python-jsonschema.readthedocs.io/) |
| NumPy | 격자, mesh와 image 효과의 수치 배열 처리 | [NumPy](https://numpy.org/doc/stable/) |
| PyVista, VTK와 Pillow | 직교 및 원근 3D 렌더링과 PNG 및 JPEG encoding | [PyVista](https://docs.pyvista.org/getting-started/installation.html), [VTK](https://docs.vtk.org/en/latest/advanced/runtime_settings.html), [Pillow](https://python-pillow.github.io/) |
| OSMesa와 EGL | CPU 및 GPU off-screen OpenGL context | [Mesa](https://docs.mesa3d.org/), [EGL Registry](https://registry.khronos.org/EGL/) |
| FastAPI, Uvicorn과 websockets | HTTP와 WebSocket service | [FastAPI](https://fastapi.tiangolo.com/), [Uvicorn](https://www.uvicorn.org/), [websockets](https://websockets.readthedocs.io/) |
| Rust, tungstenite와 V4L2 | ARM64의 bounded WebSocket bridge와 virtual camera | [Rust](https://www.rust-lang.org/), [tungstenite](https://crates.io/crates/tungstenite), [V4L2](https://www.kernel.org/doc/html/latest/userspace-api/media/v4l/v4l2.html) |

Server image의 기본 renderer는 `vtkOSOpenGLRenderWindow`와 Mesa OSMesa다.
`LIBGL_ALWAYS_SOFTWARE=1`이 GPU와 `DISPLAY` 없는 CPU 경로를 고정한다. EGL 배포는
`vtkEGLRenderWindow`와 host GPU runtime을 명시적으로 주입하며 두 renderer가 같은 VTK
window를 사용한다. Camera profile의 backend 값은 실제로 생성된 window가 배포 선택과
일치하는지 검사한다.

## 실행 단위와 데이터 흐름

제품이 관리하는 실행 단위는 다음 4개다.

| 실행 단위 | Platform | 담당 작업 |
| --- | --- | --- |
| Server 주 process | Linux AMD64 | CLI, 수신, 상태, HTTP와 두 worker 조정 |
| Browser render process | Linux AMD64 | 고정 사선 직교투영 PNG 생성 |
| Synthetic render process | Linux AMD64 | 선택적 보간 frame의 원근 JPEG 생성 |
| Edge bridge process | Linux ARM64 | WebSocket 수신, 검증과 V4L2 write |

주 process는 유효한 Observation을 최신 실행 상태로 교체한 뒤 Browser worker와 활성화된
Synthetic worker에 독립적으로 제출한다. 두 renderer가 느려져도 Receiver는 최신 pending
정책으로 입력을 계속 처리한다.

```text
Generator -> Receiver -> Validator -> Latest State
                                        |       |
                                        v       v
                                  Browser Job  Camera Timeline
                                        |       |
                                        v       v
                                    PNG Store  JPEG Store
                                        |       |
                                        v       v
                                    HTTP Page  WebSocket -> Edge Bridge -> V4L2
```

Browser worker는 처리 중 도착한 요청 중 최신 1개만 pending 상태에 둔다. Synthetic worker도
처리 중 1개와 최신 pending 1개만 유지한다. Synthetic timeline은 이전과 현재 Observation
사이에서 wall clock 기준 frame 시각을 선택하며 render 처리량이 부족하면 이미 지난 target 중
최신 1개만 제출한다.

## 메모리 상태와 상한

Server가 메모리에 유지하는 상태는 다음 6개다. 운영 데이터를 영구 저장하는 경로는 없다.

| 보관 지점 | 상한 | 상한 처리 |
| --- | --- | --- |
| 실행 상태 | Header와 최신 Observation 각 1개 | 새 실행 또는 최신 Observation으로 교체 |
| Browser render queue | 처리 중 1개와 pending 1개 | Pending을 새 요청으로 교체 |
| Browser frame | 최신 PNG 1개 | 새 revision으로 교체 |
| Camera interpolation | 이전 및 현재 Observation, bounded target | 새 구간 또는 run으로 교체 |
| Camera render queue | 처리 중 1개와 pending 1개 | Pending을 새 요청으로 교체 |
| Camera frame | 최신 JPEG 1개, 최대 4,194,304 byte | 새 revision으로 교체 |

HTTP 요청은 동시에 최대 16개를 처리하고 요청 제한 시간은 5 s다. Camera WebSocket client는
최대 4개를 허용하고 각 frame write 제한 시간은 1 s다. Mesh 생성에는 node, face와 clipping
연산량의 유한한 예산을 둔다. 실제 상한과 자원 기준은
[실행 환경](deployment.md)에서 관리한다.

## 수신과 실행 상태

Receiver는 연결별 byte buffer에서 LF로 끝난 레코드만 validator에 전달한다. Parser는 중복
JSON key와 유한하지 않은 수치를 거부한다. Schema 검사 뒤에는 좌표 증가, 높이 배열 shape,
투입구 index, sensor 방향과 경계 형상처럼 schema가 표현하지 않는 의미 제약을 검증한다.

한 입력 chunk에서 framing 한도 오류가 발생해도 오류 앞에서 완성된 레코드는 순서대로
처리한다. 한도를 초과한 레코드와 남은 buffer는 폐기하고 해당 연결을 종료한다.

유효한 Header를 수락한 뒤에만 현재 장면을 교체한다. 같은 실행의 재접속 Header는 정적
정보를 비교하고 기존 sequence 상태에 연결한다. 새 실행으로 전환하면 새 Observation을
받기 전까지 이전 실행의 두 frame 저장소를 비운다.

완성된 무효 레코드는 상태를 변경하지 않고 거부한다. Header 실패, framing 한도 초과와
연결 시작 제한 시간 초과는 해당 연결을 종료한다. 정상 Header 이후의 무효 Observation은
거부 건수를 표시하고 다음 레코드를 처리한다. 생성기에는 응답 byte를 전송하지 않는다.

각 Observation은 전체 표면 snapshot이며 이전 표면에 적용하는 변경분으로 처리하지 않는다.
주 process는 연결 상태 변경도 Browser worker에 제출하므로 새 Observation 없이 연결이
끊겨도 overlay가 갱신된다.

## Geometry와 Browser 장면

Geometry는 polygon 방향과 시작 vertex를 정규화하고 고정 순서의 ear clipping으로 바닥을
삼각분할한다. Self-intersection과 퇴화 경계는 의미 검증 오류로 처리한다.

격자는 `index = y_index * x_count + x_index` 순서로 vertex를 구성한다. 각 cell은 `(y, x)`와
`(y + 1, x + 1)`을 잇는 대각선으로 나눈다. 경계 삼각형과 표면 삼각형의 교집합을 계산하고
교차점의 Z 값은 원래 표면 삼각형에서 선형 보간한다. 교집합 polygon은 고정 순서로 다시
삼각분할한다.

표면 mesh의 외곽 edge는 각 꼭짓점에서 `floor_z_m`까지 내려 적재 체적 옆면을 구성한다.
모든 높이가 바닥과 같으면 퇴화한 옆면을 만들지 않는다. Sensor는 계약 검증에만 사용하고
Browser와 합성 camera 장면에 표시하지 않는다.

Browser camera는 거리에 따른 크기 변화를 제거한 고정 사선 직교투영을 사용한다. 기본
frame은 1280 x 720이다. Scrap은 높이에 따른 노랑, 주황과 적색을 사용하고 회색 mesh edge를
표시한다. 색상 막대는 없으며 화면 오른쪽으로 가장 먼 외벽 수직 변에 바닥, 상단과 2 m 간격
높이 눈금을 표시한다.

## 합성 camera 장면과 시간축

Synthetic renderer는 같은 geometry에 원근 camera, PBR 재질, 조명, seeded scrap 색
variation, noise와 vignette를 적용한다. Profile 좌표는 Header 경계 중심, 바닥 높이와 최대
scene span으로 변환한다. 현재 투입구에 chute를 만들고 현재 투입구가 없으면 첫 번째
투입구를 사용한다.

첫 Observation은 exact frame이다. 연속 sequence, 같은 run과 격자, 증가하는 시각과 최대
2 s 간격을 만족하면 높이와 연속 scenario 수치를 선형 보간한다. 경계를 넘는 구간은 오른쪽
Observation을 hold frame으로 사용한다. 상세 field와 reason 계약은
[합성 카메라 Live 계약](../SYNTHETIC_CAMERA_VIDEO.md)에서 관리한다.

Renderer는 Header seed와 frame 식별자로 image 효과를 결정하고 Pillow로 JPEG를 메모리에서
encoding한다. JPEG는 filesystem에 기록하지 않는다.

## 서비스 인터페이스

Visualizer가 제공하는 endpoint는 다음 6개다.

| Endpoint | 응답 |
| --- | --- |
| `GET /` | Server frame과 상태를 표시하는 Browser 화면 |
| `GET /frame.png` | 최신 직교투영 PNG와 revision, 준비 전 204 |
| `GET /status` | 연결, Observation, 두 renderer와 camera 상태 |
| `GET /camera/` | 같은 WebSocket을 사용하는 합성 camera Browser 화면 |
| `GET /camera/v1/status` | Camera pipeline 상태 |
| `WebSocket /camera/v1/stream` | Descriptor text 1개 뒤 최신 JPEG binary |

Camera 관련 3개 endpoint는 synthetic camera를 활성화한 경우에만 설치한다.

Browser는 상태를 0.5 s마다 조회하고 revision이 바뀐 경우에만 PNG를 요청한다. HTTP 요청은
보관한 최신 frame과 상태만 읽으며 렌더링을 직접 시작하지 않는다.

Camera Browser와 edge bridge는 최대 4개 client를 허용하는 같은 WebSocket을 사용한다.
Server는 최신 JPEG를 profile FPS에 맞춰 각 client에 반복 전송하므로 전송 cadence와 고유
render cadence가 분리된다. Server는 frame 전송과 client disconnect 수신을 동시에 처리하고
inbound application message는 send-only 계약 위반으로 종료한다. Uvicorn은 inbound message
4,096 byte, queue 1개와 WebSocket compression 비활성화를 적용한다. Bundled edge bridge와
연결할 때는 version 1 descriptor, 고정 endpoint, 1920 x 1080, 30 FPS와 최대 4,194,304 byte
계약을 유지한다.

## Edge device 경계

Edge host는 `v4l2loopback` module로 `/dev/video42`를 만들고 udev가
`/dev/scrap-synthetic-camera` alias를 제공한다. Module과 device format 설정은 host에서 한
번 수행한다. Systemd oneshot은 boot마다 modules-load 이후, Docker 이전에 MJPG 1920 x
1080, 30 FPS와 buffer control을 복원한다. Container에는 device 1개와 host `video` group
GID만 전달한다.

Bridge는 plain `ws://` URL만 허용하고 URL credential, query와 다른 path를 거부한다.
Descriptor와 JPEG가 계약을 벗어나면 session을 닫고 재연결한다. Network 오류는 500 ms부터
30 s까지 지수 backoff로 재시도하며 정상 frame을 기록한 session 뒤에는 backoff를 초기화한다.
Device capability, format 또는 write 오류는 process 오류로 종료한다.

## 배포 경계

Release workflow는 원격 `main`의 version tag를 입력으로 AMD64 Visualizer image, ARM64 Edge
Bridge image와 Python package를 생성한다. 각 image는 version 및 source commit tag를 같은
manifest digest에 연결하고 source, revision과 version OCI label을 기록한다.

두 GHCR(GitHub Container Registry) image에는 SBOM(Software Bill of Materials)과 build
provenance를 첨부한다. Workflow는 공개 Package와 platform을 검증하고 Visualizer image를
digest로 가져와 실제 headless rendering을 검사한 뒤에만 GitHub Release를 게시한다. 배포는
각 Release asset이 제공하는 digest 참조를 사용한다.
