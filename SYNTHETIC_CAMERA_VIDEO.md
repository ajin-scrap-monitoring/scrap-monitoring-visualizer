# 합성 카메라 Live 계약

## 문서 역할

이 문서는 Observation version 1 전체 적재면 snapshot을 현장 camera 시점의 live MJPEG
stream으로 변환하고 edge device의 V4L2 camera로 제공하는 계약의 정본이다. 환경 변수와
사용자 실행 절차는 [README](README.md), 내부 모듈 경계는
[아키텍처](docs/architecture.md)에서 관리한다.

이 기능은 camera 기반 개발과 통합 검증을 위한 합성 입력이다. 실제 현장의 색상, 반사,
가림과 camera 정확도를 증명하지 않는다. 관찰 기록, replay, MP4, depth map과 class mask는
생성하지 않는다.

## 기능 구성

전체 기능은 다음 5개 구성 요소로 동작한다.

| 구성 요소 | 책임 |
| --- | --- |
| LiDAR Simulator | Header와 시간별 전체 적재면 Observation 전송 |
| Synthetic camera pipeline | Frame 시각 선택, 보간과 bounded render 요청 관리 |
| Perspective renderer | 현장 camera 시점의 PBR(Physically Based Rendering) 장면과 JPEG 생성 |
| Camera service | 통합 Browser 화면, 상태, descriptor와 최신 JPEG 전송 |
| Rust edge bridge | Stream 검증, 재연결과 V4L2 output 기록 |

Renderer와 WebSocket은 Linux AMD64 Visualizer image에서 실행한다. Bridge는 Linux ARM64
edge image에서 실행하며 LiDAR Simulator나 실제 camera process를 변경하지 않는다.

## 입력과 profile

Pipeline 입력은 같은 run의 유효한 Header와 Observation이다. Header는 경계, 바닥, 외벽,
투입구와 좌표 기준을 제공하고 Observation은 절대 Z 높이의 전체 표면 격자와 scenario 상태를
제공한다. 이전 표면에 적용하는 변경분으로 해석하지 않는다.

Camera 설정은 Visualizer가 소유하는 version 1 JSON profile이다. Profile은 최대 65,536
byte의 UTF-8 JSON이며 중복 key, 알 수 없는 field와 유한하지 않은 숫자를 거부한다. 내장
profile은 다음 9개 설정 묶음을 가진다.

| 설정 | 내용 |
| --- | --- |
| `version` | Profile 계약 version 1 |
| `backend` | `auto`, `osmesa` 또는 `egl` render window 검증 |
| `video` | 너비, 높이, FPS, JPEG 품질과 최대 frame byte |
| `timing` | 최대 보간 간격과 구간 frame 상한 |
| `camera` | 정규화한 위치, target, view-up과 수직 화각 |
| `background_color` | 장면 배경 RGB(Red Green Blue) |
| `materials` | 바닥, 외벽, scrap과 chute의 색상, metallic과 roughness |
| `lights` | 최대 8개 조명의 정규화 위치, 색상과 강도 |
| `effects` | Seeded noise와 vignette 강도 |

정규화 camera와 조명 좌표는 적재 경계 중심, 바닥 높이와 X, Y, Z span 중 가장 큰 길이를
기준으로 scene 좌표로 변환한다. 거리는 meter, 화각은 degree를 사용한다. Camera는 원근
투영을 사용한다.

Profile 값의 상한은 다음 6개다.

| 항목 | 범위 또는 상한 |
| --- | --- |
| 영상 너비와 높이 | 각각 1부터 3,840, 1부터 2,160 |
| FPS | 1부터 60 |
| JPEG 품질 | 1부터 95 |
| JPEG byte | 최대 4,194,304 |
| 보간 구간 frame | 최대 3,000 |
| 조명 | 1개부터 8개 |

Bundled edge bridge와 연결하는 profile은 1920 x 1080, 30 FPS와 최대 4,194,304 byte를
유지해야 한다. 내장 profile은 JPEG 품질 85, 최대 보간 간격 2 s와 구간 frame 상한 120을
사용한다.

## 보간과 frame 선택

Pipeline은 첫 Observation을 그대로 렌더링한다. 그 뒤 두 Observation이 다음 5개 조건을 모두
만족하면 `scenario.elapsed_s` 기준 30 Hz frame 시각의 표면 높이를 선형 보간한다.

1. 같은 `run_id`
2. 정확히 1 증가하는 sequence
3. 증가하는 simulation 시각
4. 같은 X와 Y 좌표, cell 크기와 높이 배열 shape
5. Profile의 최대 보간 간격 이내인 simulation 시각 차이

보간 frame은 `surface.heights_m`, `surface_updated_at_s`, `surface_fill_ratio`와
`surface_volume_m3`를 선형 보간한다. `phase`, `cycle_index`와 투입구 상태는 구간의 왼쪽
Observation 값을 유지하고 오른쪽 끝 시각에는 오른쪽 Observation 전체를 사용한다.

조건을 충족하지 않거나 구간 frame 수가 상한을 넘으면 중간 상태를 만들지 않고 오른쪽
Observation을 `hold` mode로 렌더링한다. 상태 응답의
`camera_interpolation_reason`은 `run`, `sequence`, `time`, `grid`, `gap` 또는
`frame_limit`을 기록한다.

Pipeline은 wall clock에서 해당 simulation 간격만큼 frame 시각을 진행한다. Synthetic
renderer는 처리 중 1개와 최신 pending 1개만 유지한다. 새 요청이 도착하면 오래된 pending
요청을 교체하므로 느린 renderer가 Observation 수신을 막거나 제한 없이 backlog를 만들지
않는다.

WebSocket의 30 FPS는 30개의 binary message를 1초에 전송하는 cadence 계약이다. 최신 JPEG가
바뀌지 않은 구간에는 같은 byte를 반복 전송한다. GPU나 CPU가 모든 보간 시각을 렌더링하지
못하면 중간 frame은 교체될 수 있으므로 30개의 고유 장면을 매초 보장하지 않는다.

## 렌더링

Renderer는 같은 geometry 경계에서 바닥, 외벽, 적재 체적, scrap 표면과 chute를 구성한다.
Chute 상단 mount는 투입구 좌표 평균에 고정한다. 하단 outlet의 중심은 현재 투입구 좌표에
두고 투입구 index가 증가할 때 시계방향 자세를 선택한다. Collecting 상태처럼 현재 투입구가
없으면 첫 번째 투입구를 사용한다.
Scrap 표면에는 높이 색 범례나 Browser overlay를 넣지 않는다. Camera profile이 지정한 원근
시점, PBR 재질과 조명을 사용하고 Header seed와 frame 식별자로 결정되는 scrap 색 variation,
noise와 vignette를 적용한다.

같은 Header, Observation, profile과 renderer version은 같은 mesh, camera 배치와 seeded
효과 값을 만든다. 내장 profile은 고유 frame 처리량을 위해 noise와 vignette를 0으로 두며
사용자 profile에서 활성화할 수 있다. VTK version과 GPU driver 차이까지 포함한 JPEG byte
동일성은 보장하지 않는다.

`osmesa`는 `vtkOSOpenGLRenderWindow`, `egl`은 `vtkEGLRenderWindow`가 실제로 생성됐는지
검사한다. `auto`는 VTK가 선택한 window를 허용한다. Server image의 기본 환경은 GPU와
`DISPLAY`가 없는 OSMesa CPU 경로다. EGL 경로의 host 요구조건과 환경 변수는
[README](README.md#egl과-gpu)를 따른다.

## Browser와 WebSocket 계약

Camera service의 고정 endpoint는 다음 2개다.

| Endpoint | 응답 |
| --- | --- |
| `GET /camera/v1/status` | Pipeline, frame, backend와 최근 오류 상태 JSON |
| `WebSocket /camera/v1/stream` | Descriptor text 뒤 최신 JPEG binary stream |

Application 인증과 TLS(Transport Layer Security)는 제공하지 않는다. 루트 Browser 화면과
edge bridge는 같은 WebSocket endpoint를 사용하며 동시 client는 최대 4개다. 다섯 번째
client는 WebSocket code 1013으로 종료한다.

Server는 내장 edge 호환 profile에서 연결을 수락한 뒤 첫 message로 다음 UTF-8 text
descriptor를 보낸다. 사용자 profile은 같은 field에 설정한 영상 값을 넣으며 bundled edge
bridge는 아래 값과 정확히 같은 descriptor만 수락한다.

```json
{"type":"camera_stream_descriptor","version":1,"format":"MJPEG","width":1920,"height":1080,"fps":30,"max_frame_bytes":4194304}
```

이후 message는 SOI(Start Of Image) `FF D8`로 시작하고 EOI(End Of Image) `FF D9`로 끝나는
완전한 JPEG binary 1개다. 한 JPEG는 최대 4,194,304 byte다. Server는 WebSocket write가
1 s 안에 끝나지 않거나 client가 연결을 끊으면 session을 종료한다. Server는 frame 전송과
client disconnect 수신을 동시에 처리한다. Client가 application text 또는 binary message를
보내면 send-only 계약 위반으로 code 1003을 반환한다. Server의 inbound message는 4,096
byte와 queue 1개로 제한하고 WebSocket compression은 사용하지 않는다.

Camera 상태는 설정한 형식과 해상도, 최신 frame revision, source sequence와 simulation
시각, 실제 render window, 보간 mode, 제출 및 완료 frame 수, 교체된 pending 수와 최근
오류를 제공한다.

## Edge bridge와 V4L2 계약

Bridge는 연결마다 첫 text message 1개를 최대 4,096 byte로 제한하고 descriptor의 모든 값을
정확히 검증한다. 그 뒤 text message와 descriptor 전에 도착한 binary message를 거부한다.
JPEG를 decode하거나 다시 encode하지 않고 marker와 SOF(Start Of Frame)에 기록된 1920 x
1080 크기를 검증한 뒤 V4L2 output에 기록한다.

Host virtual camera의 고정 계약은 다음 8개다.

| 항목 | 값 |
| --- | --- |
| Kernel module | `v4l2loopback` |
| Device node | `/dev/video42` |
| Semantic alias | `/dev/scrap-synthetic-camera` |
| Card label | `Scrap Synthetic Camera` |
| Pixel format | `MJPG` |
| Frame | 1920 x 1080, 30 FPS |
| Buffer 정책 | `max_buffers=2`, `keep_format=1`, `sustain_framerate=0` |
| Boot 복원 | modules-load 이후, Docker 이전 systemd oneshot |

Bridge는 시작할 때 device가 character device인지, V4L2 video output과 read/write I/O를
지원하는지, 현재 output format이 계약과 같은지 검사한다. Device 오류는 process를 종료하고
network, WebSocket 또는 protocol 오류와 1 s message timeout은 bounded 지수 backoff로
재연결한다. 첫 유효 frame을 기록하면 backoff를 최소값으로 되돌린다. SIGINT와 SIGTERM은
현재 session과 device를 닫고 정상 종료한다.

Bridge는 최신 frame 1개만 보관하고 절대 deadline을 기준으로 30 Hz로 기록한다. 늦은 주기는
건너뛰며 backlog를 만들거나 한 번에 여러 frame을 기록하지 않는다. Host setup은 systemd
service를 활성화해 재부팅할 때마다 module 적재 뒤 device format과 buffer control을 복원하고
그 뒤 Docker를 시작한다.

V4L2 loopback은 각 capture buffer에 연속 sequence와 edge host의 monotonic EOF(End Of Frame)
timestamp를 제공한다. 이는 일반 camera consumer가 시간순 정렬에 사용하는 V4L2 metadata다.
UVC(USB Video Class) hardware의 PTS(Presentation Time Stamp), STC(Source Time Clock)와 USB
SOF(Start Of Frame) counter는 합성하지 않는다.

## 상태와 저장 경계

합성 camera가 메모리에 유지하는 운영 상태는 다음 4개다.

| 보관 지점 | 상한 |
| --- | --- |
| 보간 입력 | 이전 및 현재 Observation 각 1개 |
| Frame target | 구간당 내장 profile 기준 최대 120개 |
| Render 요청 | 처리 중 1개와 pending 1개 |
| Stream frame | 최신 JPEG 1개, 최대 4,194,304 byte |

새 run이나 source 연결 중단을 수락하거나 합성 render가 실패하면 target과 최신 JPEG를
제거한다. 이전 JPEG를 받은 WebSocket session은 source가 없어지면 종료된다. 합성 renderer
process가 종료되면 Visualizer도 오류로 종료돼 Container restart 정책이 전체 process를 다시
시작한다. 운영 Observation, JPEG와 영상은 Container filesystem, host volume이나 Git에
저장하지 않는다.

## 검증

자동 검증은 다음 10개 경계를 확인한다.

1. Profile 크기, JSON 구조, field와 수치 상한
2. 같은 격자의 선형 높이와 scenario 수치 보간
3. Run, sequence, 시각, 격자와 긴 간격 경계의 보간 금지
4. Frame target 및 render queue 상한과 최신 요청 교체
5. 원근 camera, scene actor, PBR 재질과 JPEG 형식
6. OSMesa와 EGL render window 일치 검사
7. Descriptor 우선순위, WebSocket client 상한과 30 Hz 반복 전송
8. Rust descriptor, JPEG marker, 크기와 byte 상한 검증
9. V4L2 capability, FourCC, 해상도와 device 오류 처리
10. 실제 V4L2 camera의 90 frame capture, cadence, packet 수, decode, sequence와 timestamp

Pixel 전체 snapshot은 사용하지 않는다. 실제 장비 검증은
`deploy/edge/check-90-frames.sh`로 90개 MJPEG frame을 2.5 s부터 5 s 안에 받고 모두 decode할
수 있는지 확인한다.
