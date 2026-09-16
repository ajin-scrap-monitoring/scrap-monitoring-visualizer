# 개발 계획

## 문서 역할

이 문서는 현재 구현 상태, 작업 순서와 단계별 완료 조건의 정본이다. 초기 제품 범위는
[프로젝트 명세](project-spec.md), 구현 설계는 [아키텍처](architecture.md), 합성 camera
외부 계약은 [합성 카메라 Live 계약](../SYNTHETIC_CAMERA_VIDEO.md)을 따른다.

## 현재 상태

전체 구현은 P0부터 P8까지 9개 단계다. 각 단계의 산출물은 source와 배포 파일에 반영되어
있으며 P8은 릴리스와 실제 장비 검증 조건을 추가로 정의한다.

현재 source는 Observation version 1을 받아 다음 2개 live 출력을 만든다.

| 출력 | 현재 구현 |
| --- | --- |
| Browser preview | 고정 사선 직교투영 3D frame, 합성 camera live 영상과 상태의 단일 페이지 |
| Synthetic camera | 1920 x 1080 30 FPS MJPEG와 ARM64 V4L2 bridge |

관찰 기록, replay, MP4, 상면 Browser 화면, depth map과 class mask는 제공하지 않는다.
`docs/project-spec.md`는 고정 입력이므로 수정하지 않는다. 현재 제품 결정과 다른 고정 명세
항목은 이 계획에서 완료 조건으로 사용하지 않는다.

Release target은 `v2.0.0`이며 CI(Continuous Integration), CodeQL, 두 image의 릴리스 정책
검사와 실제 90 frame 검증을 완료 조건으로 사용한다.

## 단계와 선행 관계

| 단계 | 작업 단위 | 선행 단계 | 구현 상태 |
| --- | --- | --- | --- |
| P0 | 에이전트 지침, 계약 기준과 구현 계획 | 없음 | 구현 |
| P1 | 실행 환경과 headless 렌더링 | P0 | 구현 |
| P2 | 계약 parser와 실행 상태 판정 | P1 | 구현 |
| P3 | TCP(Transmission Control Protocol) 수신 | P2 | 구현 |
| P4 | 결정론적인 mesh와 Browser 장면 | P1, P2 | 구현 |
| P5 | Live CLI(Command-Line Interface)와 HTTP(Hypertext Transfer Protocol) preview | P3, P4 | 구현 |
| P6 | AMD64 Container, CI와 릴리스 | P5 | 구현 |
| P7 | 환경 변수와 사용자 배포 절차 | P6 | 구현 |
| P8 | 합성 camera, ARM64 edge bridge와 두 image 릴리스 | P3, P4, P6, P7 | 구현 |

각 변경은 조직 공통 양식의 이슈, 이슈 번호가 포함된 branch, Conventional Commit, PR(Pull
Request), CI와 CodeQL, squash merge 순서로 진행한다. Release tag는 원격 `main`의 검증된
version commit에만 생성한다.

## P0. 프로젝트 기준

| 구분 | 내용 |
| --- | --- |
| 산출물 | 에이전트 정본과 진입점, 계약 사본과 출처, 저장소 및 릴리스 검사 |
| 완료 조건 | 심링크, 명세 원본, 계약 byte, schema와 문서 검사 통과 |

## P1. 실행 환경과 headless 렌더링

| 구분 | 내용 |
| --- | --- |
| 산출물 | Python package, 고정 lockfile과 OSMesa off-screen 렌더링 |
| 완료 조건 | Linux AMD64 비root Container에서 GPU와 `DISPLAY` 없이 실제 PNG 생성 |

개발 검사 도구는 Ruff, mypy, pytest와 rumdl의 4개다. CI는 저장소 검사, 정적 검사, 전체
테스트와 실제 Container 검사를 `CI` job으로 집계한다.

## P2. 계약 parser와 실행 상태 판정

| 구분 | 내용 |
| --- | --- |
| 산출물 | 불변 record model, schema validator, 의미 검사와 실행 상태 전이 |
| 검증 | Field 오류, 중복 key, 비유한 수치, 배열 shape, sensor, 투입구, sequence와 run 전환 |
| 완료 조건 | 설치 package와 고정 계약 사본을 사용하는 계약 및 상태 검사 통과 |

## P3. TCP 수신

| 구분 | 내용 |
| --- | --- |
| 산출물 | 단일 producer 수신기, LF(Line Feed) 조립기와 재접속 처리 |
| 검증 | Packet 분할 및 병합, line 상한, 추가 연결 거부, TCP 응답 byte 부재 |
| 완료 조건 | 느린 renderer 상황에도 bounded memory와 수신 진행 유지 |

## P4. Mesh와 Browser 장면

| 구분 | 내용 |
| --- | --- |
| 산출물 | 표면, 적재 체적, 바닥, 외벽, 투입구, 직교투영 camera와 overlay |
| 검증 | Y-major 격자, 비영점 바닥, concave 경계, clipping과 퇴화 입력 |
| 완료 조건 | 구조 및 수치 검사와 실제 1280 x 720 사선 PNG 생성 |

Browser 화면은 적재 공간과 scrap을 단일 3D frame으로 표시한다. 화면상 오른쪽 외벽 변에는
바닥, 상단과 2 m 간격 높이 눈금을 표시하고 sensor와 색상 범례는 표시하지 않는다.

## P5. Live CLI와 HTTP preview

| 구분 | 내용 |
| --- | --- |
| 산출물 | Live CLI, 최신 PNG 저장소, 상태 endpoint와 Browser 화면 |
| 검증 | 준비 전 상태, revision, sequence, 연결 중단, 새 run과 느린 Browser 격리 |
| 완료 조건 | 실제 TCP 및 HTTP 통합 검사와 Live 설정 오류 검사 통과 |

## P6. AMD64 Container, CI와 릴리스

| 구분 | 내용 |
| --- | --- |
| 산출물 | Linux AMD64 image, CI, Release workflow와 의존성 고지 |
| 검증 | 비root, read-only root, TCP 및 HTTP port, version, digest, OCI label과 attestation |
| 완료 조건 | 고정 digest image의 수신, Browser preview와 공개 Package 확인 |

## P7. 환경 변수와 사용자 배포 절차

| 구분 | 내용 |
| --- | --- |
| 산출물 | Visualizer 환경 변수, `.env.example`, README와 배포 문서 |
| 검증 | 필수값, 숫자 변환, CLI override, endpoint 충돌과 환경 변수 기반 통합 |
| 완료 조건 | README 실행 절차와 전체 자동 검사 통과 |

## P8. 합성 camera와 edge bridge

P8 구현 산출물은 다음 8개다.

| 산출물 | 현재 상태 |
| --- | --- |
| Version 1 camera profile과 내장 현장 시점 | 구현 |
| 연속 Observation의 30 Hz frame 선택과 bounded 보간 | 구현 |
| 원근 PBR 장면, seeded 효과와 JPEG encoding | 구현 |
| 최신 JPEG WebSocket, 통합 Browser 화면과 camera 상태 endpoint | 구현 |
| Rust descriptor 및 JPEG validator와 재연결 | 구현 |
| `/dev/video42` V4L2 writer와 semantic alias 설정 | 구현 |
| Linux ARM64 edge image와 Compose 배포 파일 | 구현 |
| 두 OCI image Release workflow와 asset | 구현 |

P8의 로컬 검증 순서는 다음 5단계다.

1. Python format, lint, type, 단위 및 통합 test 실행
2. Rust format, Clippy, test와 release binary build 실행
3. AMD64 headless server image에서 PNG와 합성 JPEG 생성
4. QEMU 기반 Linux ARM64 edge image build
5. Markdown, Repository 경계와 release policy 검사

P8 완료 조건은 다음 7개다.

1. PR의 필수 `CI`와 CodeQL 검사 통과
2. 원격 `main` squash merge와 이슈 및 Project 상태 완료
3. Release 전 version, tag ancestry, 두 image platform, SBOM과 provenance logic 재검토
4. `v2.0.0` tag 1개를 통한 GitHub Release와 Public GHCR image 2개 게시
5. Release asset digest를 사용하는 AMD64 server와 ARM64 edge device 배포
6. Edge V4L2 camera의 MJPEG 1920 x 1080 frame 90개를 2.5 s부터 5 s 안에 수신하고 decode
7. 연결 중단과 재연결, camera 상태, server 및 edge 자원 사용 확인

## 요구사항 검증 대응

현재 제품 검증은 다음 12개 범주로 구성한다.

| 범주 | 담당 단계 | 검증 경계 |
| --- | --- | --- |
| Observation fixture와 schema | P2 | `tests/contract/` |
| Framing과 최대 line | P3 | `tests/unit/`, `tests/integration/` |
| Version, type과 field 오류 | P2 | `tests/contract/`, `tests/unit/` |
| Sequence와 run 전환 | P2, P3 | `tests/unit/`, `tests/integration/` |
| 표면 mesh와 clipping | P4 | `tests/unit/` |
| Browser queue, frame과 해상도 | P4, P5 | `tests/unit/`, `tests/integration/` |
| Live 설정과 오류 종료 | P5, P7 | `tests/unit/` |
| HTTP 상태와 Browser 격리 | P5 | `tests/integration/` |
| Camera profile, 보간과 scheduler | P8 | `tests/unit/` |
| 원근 JPEG와 WebSocket | P8 | `tests/unit/`, `tests/integration/` |
| Rust descriptor, JPEG, backoff와 V4L2 | P8 | `edge-bridge/src/` unit test |
| 두 platform image와 release policy | P8 | `tools/tests/`, CI와 실제 장비 |

Container 검증은 `scripts/check-headless-container.sh`에서 실제 OSMesa 실행 경계를 확인한다.
단위 및 통합 test는 외부 network, 실제 host 정보나 형제 프로젝트 설치 상태에 의존하지
않는다.
