"""Validate the synthetic camera renderer inside the release image."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass, replace
from io import BytesIO
from pathlib import Path

from PIL import Image

from scrap_monitoring_visualizer.contracts import ContractParser, Header, Observation

from .models import SyntheticCameraConfig
from .renderer import VtkPbrRenderer


@dataclass(frozen=True, slots=True)
class SyntheticCameraProbeResult:
    width: int
    height: int
    format: str
    perspective: bool
    render_backend: str
    frame_bytes: int
    frame_path: str


def run_probe(
    output_dir: Path,
    contract_root: Path,
) -> SyntheticCameraProbeResult:
    output_dir.mkdir(parents=True, exist_ok=False)
    parser = ContractParser(contract_root)
    records = tuple(
        parser.parse_line(line).value
        for line in (contract_root / "fixtures/observation.v1.jsonl")
        .read_bytes()
        .splitlines(keepends=True)
    )
    header, observation = records
    if not isinstance(header, Header) or not isinstance(observation, Observation):
        raise RuntimeError("contract fixture does not contain a header and observation")
    config = SyntheticCameraConfig.from_file()
    config = replace(
        config,
        video=replace(config.video, width=640, height=360),
    )
    renderer = VtkPbrRenderer()
    try:
        frame = renderer.render(header, observation, config)
    finally:
        renderer.close()
    with Image.open(BytesIO(frame.jpeg)) as image:
        image.load()
        if image.format != "JPEG" or image.size != (640, 360):
            raise RuntimeError("synthetic camera produced an unexpected JPEG")
    frame_path = output_dir / "camera.jpg"
    frame_path.write_bytes(frame.jpeg)
    result = SyntheticCameraProbeResult(
        width=frame.width,
        height=frame.height,
        format="MJPEG",
        perspective=True,
        render_backend=frame.render_backend,
        frame_bytes=len(frame.jpeg),
        frame_path=frame_path.name,
    )
    (output_dir / "camera.json").write_text(
        json.dumps(asdict(result), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("/tmp/camera-probe"))
    parser.add_argument(
        "--contracts",
        type=Path,
        default=Path("/app/contracts/observation/v1"),
    )
    args = parser.parse_args()
    print(json.dumps(asdict(run_probe(args.output, args.contracts)), sort_keys=True))


if __name__ == "__main__":
    main()
