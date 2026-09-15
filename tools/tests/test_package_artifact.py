from __future__ import annotations

import json
import subprocess
import tomllib
import zipfile
from pathlib import Path


def test_wheel_contains_fixed_contract_schemas(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[2]
    subprocess.run(
        ["uv", "build", "--wheel", "--out-dir", str(tmp_path)],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    wheel = next(tmp_path.glob("*.whl"))
    package = "scrap_monitoring_visualizer/contracts/schema/v1"

    with zipfile.ZipFile(wheel) as archive:
        for name in ("header.schema.json", "observation.schema.json"):
            packaged = archive.read(f"{package}/{name}")
            fixed = (root / "contracts/observation/v1" / name).read_bytes()
            assert packaged == fixed


def test_edge_bridge_release_inputs_are_locked() -> None:
    root = Path(__file__).resolve().parents[2]
    with (root / "edge-bridge/Cargo.toml").open("rb") as source:
        manifest = tomllib.load(source)
    with (root / "edge-bridge/Cargo.lock").open("rb") as source:
        lockfile = tomllib.load(source)

    package_identity = (
        manifest["package"]["name"],
        manifest["package"]["version"],
    )
    locked_packages = {
        (package["name"], package["version"]) for package in lockfile["package"]
    }
    assert package_identity in locked_packages

    dockerfile = (root / "Dockerfile.edge-bridge").read_text(encoding="utf-8")
    for command in (
        "cargo fmt --all -- --check",
        "cargo clippy --locked --all-targets --all-features -- -D warnings",
        "cargo test --locked --all-targets --all-features",
        "cargo build --locked --release",
    ):
        assert command in dockerfile
    assert "licenses/THIRD_PARTY_NOTICES.html" in dockerfile
    assert "RUST_COPYRIGHT.html" in dockerfile


def test_edge_bridge_notices_cover_locked_runtime_crates() -> None:
    root = Path(__file__).resolve().parents[2]
    metadata = json.loads(
        subprocess.run(
            [
                "cargo",
                "metadata",
                "--manifest-path",
                "edge-bridge/Cargo.toml",
                "--locked",
                "--all-features",
                "--filter-platform",
                "aarch64-unknown-linux-gnu",
                "--format-version",
                "1",
            ],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout
    )
    notices = (root / "licenses/THIRD_PARTY_NOTICES.html").read_text(encoding="ascii")

    packages = {package["id"]: package for package in metadata["packages"]}
    nodes = {node["id"]: node for node in metadata["resolve"]["nodes"]}
    pending = [metadata["resolve"]["root"]]
    runtime_package_ids: set[str] = set()
    while pending:
        package_id = pending.pop()
        if package_id in runtime_package_ids:
            continue
        runtime_package_ids.add(package_id)
        pending.extend(
            dependency["pkg"]
            for dependency in nodes[package_id]["deps"]
            if any(
                dependency_kind["kind"] is None
                for dependency_kind in dependency["dep_kinds"]
            )
        )

    for package_id in runtime_package_ids:
        package = packages[package_id]
        if not package.get("source"):
            continue
        identity = f"{package['name']} {package['version']}"
        assert identity in notices
