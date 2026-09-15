# 의존성

## 직접 의존성

Repository가 직접 선택한 의존성은 server runtime 12개, edge build 및 runtime 6개, package
build와 개발 검사 8개, GitHub Actions와 image build 도구 10개로 총 36개다.

### Server runtime

| 의존성 | 버전 | 목적 | 공식 출처 | 라이선스 |
| --- | --- | --- | --- | --- |
| Python | 3.14.7 | Visualizer 실행 | [Python](https://www.python.org/downloads/release/python-3147/) | PSF-2.0 |
| FastAPI | 0.141.1 | HTTP와 WebSocket application | [PyPI](https://pypi.org/project/fastapi/0.141.1/) | MIT |
| jsonschema | 4.26.0 | 고정 계약 schema 검증 | [PyPI](https://pypi.org/project/jsonschema/4.26.0/) | MIT |
| NumPy | 2.5.3 | 격자, mesh와 image 효과 수치 배열 | [PyPI](https://pypi.org/project/numpy/2.5.3/) | BSD-3-Clause |
| Pillow | 12.3.0 | PNG와 JPEG memory encoding | [PyPI](https://pypi.org/project/pillow/12.3.0/) | MIT-CMU |
| PyVista | 0.49.0 | VTK scene과 off-screen rendering 경계 | [PyPI](https://pypi.org/project/pyvista/0.49.0/) | MIT |
| Uvicorn | 0.52.4 | HTTP와 WebSocket ASGI server | [PyPI](https://pypi.org/project/uvicorn/0.52.4/) | BSD-3-Clause |
| websockets | 17.1 | Uvicorn WebSocket protocol runtime | [PyPI](https://pypi.org/project/websockets/17.1/) | BSD-3-Clause |
| VTK | 9.7.0 | 직교 및 원근 3D rendering | [PyPI](https://pypi.org/project/vtk/9.7.0/) | BSD-3-Clause |
| Mesa `libosmesa6` | 22.3.6-1+deb12u2 | CPU off-screen OpenGL context | [Debian](https://packages.debian.org/bookworm/libosmesa6) | MIT 및 구성 요소별 라이선스 |
| GLVND `libegl1` | 1.6.0-1 | EGL vendor-neutral dispatch | [Debian](https://packages.debian.org/bookworm/libegl1) | MIT 및 구성 요소별 라이선스 |
| GLVND `libgl1` | 1.6.0-1 | OpenGL vendor-neutral dispatch | [Debian](https://packages.debian.org/bookworm/libgl1) | MIT 및 구성 요소별 라이선스 |

Server image가 설치하는 Python distribution과 Debian package의 전이 의존성은 image 내부
license notice와 SBOM(Software Bill of Materials)에 포함한다.

### Edge build와 runtime

| 의존성 | 버전 | 목적 | 공식 출처 | 라이선스 |
| --- | --- | --- | --- | --- |
| Rust | 1.96 | Linux ARM64 bridge build | [Rust](https://www.rust-lang.org/) | Apache-2.0 OR MIT |
| libc | 0.2.175 | V4L2 ioctl과 file descriptor 경계 | [crates.io](https://crates.io/crates/libc/0.2.175) | Apache-2.0 OR MIT |
| serde | 1.0.228 | Descriptor 자료형 역직렬화 | [crates.io](https://crates.io/crates/serde/1.0.228) | Apache-2.0 OR MIT |
| serde_json | 1.0.145 | Strict JSON descriptor parsing | [crates.io](https://crates.io/crates/serde_json/1.0.145) | Apache-2.0 OR MIT |
| signal-hook | 0.3.18 | SIGINT와 SIGTERM 종료 처리 | [crates.io](https://crates.io/crates/signal-hook/0.3.18) | Apache-2.0 OR MIT |
| tungstenite | 0.28.0 | Plain WebSocket client와 message 제한 | [crates.io](https://crates.io/crates/tungstenite/0.28.0) | Apache-2.0 OR MIT |

Tungstenite는 default feature와 TLS feature를 끄고 handshake feature만 사용한다. Rust direct
및 transitive crate는 `edge-bridge/Cargo.lock`에 고정한다. Edge runtime image는 build
toolchain 없이 release binary와 Debian runtime만 포함한다.

### Package build와 개발 검사

| 의존성 | 버전 | 목적 | 공식 출처 | 라이선스 |
| --- | --- | --- | --- | --- |
| uv 및 uv_build | 0.12.13 | 환경 설치, lockfile과 Python package build | [GitHub](https://github.com/astral-sh/uv) | Apache-2.0 OR MIT |
| mypy | 2.3.1 | Python 정적 타입 검사 | [PyPI](https://pypi.org/project/mypy/2.3.1/) | MIT |
| pytest | 9.1.1 | Python 자동 test | [PyPI](https://pypi.org/project/pytest/9.1.1/) | MIT |
| Ruff | 0.16.6 | Python format과 lint | [PyPI](https://pypi.org/project/ruff/0.16.6/) | MIT |
| rumdl | 0.2.70 | Markdown 검사 | [PyPI](https://pypi.org/project/rumdl/0.2.70/) | MIT |
| types-jsonschema | 4.26.0.20260518 | jsonschema 타입 정보 | [PyPI](https://pypi.org/project/types-jsonschema/4.26.0.20260518/) | Apache-2.0 |
| cargo-about | 0.9.2 | Rust 직접 및 전이 crate license 감사와 고지 생성 | [crates.io](https://crates.io/crates/cargo-about/0.9.2) | Apache-2.0 OR MIT |
| cargo-audit | 0.22.2 | RustSec 취약점 database 기반 lockfile 감사 | [crates.io](https://crates.io/crates/cargo-audit/0.22.2) | Apache-2.0 OR MIT |

Rust format과 lint는 Rust 1.96 toolchain의 rustfmt와 Clippy component를 사용한다.
`cargo-about`은 허용한 license 집합을 검사하고 `licenses/THIRD_PARTY_NOTICES.html`을 생성한다.
`cargo-audit`은 `edge-bridge/Cargo.lock`을 RustSec advisory database와 대조한다.

### GitHub Actions와 image build 도구

| 의존성 | 버전 | 목적 | 공식 출처 | 라이선스 |
| --- | --- | --- | --- | --- |
| actions/checkout | v6.1.0 | 저장소와 tag 이력 조회 | [GitHub](https://github.com/actions/checkout) | MIT |
| actions/setup-python | v6.3.0 | 검사 Python 설치 | [GitHub](https://github.com/actions/setup-python) | MIT |
| astral-sh/setup-uv | v10.0.1 | uv 설치와 package cache | [GitHub](https://github.com/astral-sh/setup-uv) | MIT |
| docker/setup-qemu-action | v4.4.0 | ARM64 image emulation 구성 | [GitHub](https://github.com/docker/setup-qemu-action) | Apache-2.0 |
| tonistiigi/binfmt | qemu-v10.2.3-68 | ARM64 실행용 QEMU static binary 등록 | [GitHub](https://github.com/tonistiigi/binfmt) | MIT |
| docker/setup-buildx-action | v4.4.0 | Multi-platform OCI builder | [GitHub](https://github.com/docker/setup-buildx-action) | Apache-2.0 |
| Docker Buildx | v0.37.1 | 고정 BuildKit builder 생성과 image build 제어 | [GitHub](https://github.com/docker/buildx) | Apache-2.0 |
| Moby BuildKit | v0.33.0 | GitHub Actions의 고정 container image builder | [GitHub](https://github.com/moby/buildkit) | Apache-2.0 |
| docker/login-action | v4.6.0 | GHCR 인증 | [GitHub](https://github.com/docker/login-action) | Apache-2.0 |
| docker/build-push-action | v7.4.0 | 두 OCI image, SBOM과 provenance build | [GitHub](https://github.com/docker/build-push-action) | Apache-2.0 |

Python direct 및 transitive 의존성과 file hash는 `uv.lock`에 고정한다. Container base와 uv 및
Rust image는 Dockerfile에서 digest로 고정하고 GitHub Actions는 workflow에서 commit hash로
고정한다.

## Edge host 의존성

Edge host의 one-time 설정과 검증은 다음 4개 package 묶음을 사용한다. 이 package는 edge
Container image에 포함하지 않으며 설치 대상 Linux distribution의 package version과
license metadata를 따른다.

| Package | 용도 |
| --- | --- |
| 현재 kernel header | `v4l2loopback` DKMS build |
| `v4l2loopback-dkms`, `v4l2loopback-utils` | Virtual camera kernel module과 도구 |
| `v4l-utils` | V4L2 format, FPS와 control 설정 |
| FFmpeg와 `ffprobe` | 실제 90 frame capture와 decode 검증 |

## 고정 환경 검증

Python 환경과 전체 source 검사를 실행한다.

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
```

Rust 고정 의존성과 release binary를 Container에서 검사한다.

```bash
docker build \
  --file Dockerfile.edge-bridge \
  --target test \
  --tag scrap-monitoring-visualizer-edge-bridge:test \
  .
```

Server runtime 의존성과 실제 OSMesa frame을 검사한다.

```bash
scripts/check-headless-container.sh
```

CI는 같은 검사를 수행하고 Linux ARM64 edge runtime image를 추가로 빌드한다. Release는 두
image에 각각 SBOM과 provenance를 첨부한다. Visualizer image의
`dependency_audit.py`는 CPython, Python distribution과 직접 선택한 Debian package version
및 notice 경로를 `dependency-inventory.json`으로 출력한다. Edge image는 생성한 crate 고지와
Rust toolchain의 `COPYRIGHT.html`을 `/usr/share/doc/scrap-synthetic-camera-bridge/`에 포함한다.
