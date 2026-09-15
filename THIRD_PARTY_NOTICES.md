# Third-party notices

이 프로젝트 소스에는 별도 라이선스를 부여하지 않는다. 외부 의존성에는 각 저작권자와
배포자가 정한 라이선스를 적용한다.

배포 산출물은 AMD64 Visualizer image와 ARM64 Edge Bridge image의 2개다. 각 image에 연결된
SBOM(Software Bill of Materials)은 직접 및 전이 구성 요소의 이름과 version을 기록한다.
Build provenance는 해당 image를 만든 source와 build 정보를 기록한다.

Visualizer image에 설치된 Python distribution의 license와 notice 원문은
`/app/.venv/lib/python3.14/site-packages/*-*.dist-info/` 아래의 `LICENSE`, `COPYING`과
`NOTICE` 계열 파일에 포함된다. WebSocket server가 직접 사용하는 `websockets` distribution도
이 경로와 Visualizer dependency inventory에 포함된다. Debian package의 저작권과 license 원문은
`/usr/share/doc/<package>/copyright`에 포함된다.

Edge Bridge의 Rust direct 및 transitive crate version은 `edge-bridge/Cargo.lock`에 고정한다.
`cargo-about`이 허용한 license를 검사하고 [crate 고지](licenses/THIRD_PARTY_NOTICES.html)를
생성한다. Edge image는 이 고지와 Rust toolchain의 `COPYRIGHT.html`을
`/usr/share/doc/scrap-synthetic-camera-bridge/`에 포함한다. Edge runtime Debian package의
원문 notice는 image의 `/usr/share/doc/` 아래에 있다.

Release asset의 `dependency-inventory.json`은 Visualizer image에서 읽은 CPython, Python
distribution, 직접 선택한 Debian package version과 각 notice 경로를 기록한다. 두 image의
직접 의존성 version, 목적, 출처와 license는 [의존성 문서](docs/dependencies.md)에서
관리한다.

Edge host에 별도로 설치하는 kernel header, `v4l2loopback`, V4L2 도구와 FFmpeg는 image에
포함되지 않는다. 해당 host package의 license와 notice는 설치 대상 Linux distribution의
package metadata와 `/usr/share/doc/`에서 확인한다.
