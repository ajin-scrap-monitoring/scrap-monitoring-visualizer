from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from scrap_monitoring_visualizer.contracts import ContractParser, Header, Observation
from scrap_monitoring_visualizer.synthetic_camera import SyntheticCameraConfig
from scrap_monitoring_visualizer.synthetic_camera.renderer import (
    _apply_effects,
    _chute_poly_data,
    _validate_render_window,
    camera_placement,
)

CONTRACT_ROOT = Path("contracts/observation/v1")


def _header() -> Header:
    parser = ContractParser(CONTRACT_ROOT)
    line = (
        (CONTRACT_ROOT / "fixtures/observation.v1.jsonl")
        .read_bytes()
        .splitlines(keepends=True)[0]
    )
    parsed = parser.parse_line(line).value
    assert isinstance(parsed, Header)
    return parsed


def test_camera_profile_produces_overhead_perspective_placement() -> None:
    config = SyntheticCameraConfig.from_file()
    header = _header()
    placement = camera_placement(header, config)

    minimum_y = min(point[1] for point in header.scene.boundary_xy_m)
    maximum_y = max(point[1] for point in header.scene.boundary_xy_m)
    assert placement.position[2] > header.scene.top_z_m
    assert minimum_y < placement.position[1] < maximum_y
    assert 45.0 < config.camera.view_angle_deg < 60.0


def test_chute_size_uses_planar_span_and_hangs_below_wall_top() -> None:
    parser = ContractParser(CONTRACT_ROOT)
    lines = (
        (CONTRACT_ROOT / "fixtures/observation.v1.jsonl")
        .read_bytes()
        .splitlines(keepends=True)
    )
    header = parser.parse_line(lines[0]).value
    observation = parser.parse_line(lines[1]).value
    assert isinstance(header, Header)
    assert isinstance(observation, Observation)
    header = replace(
        header,
        scene=replace(
            header.scene,
            boundary_xy_m=(
                (0.0, 0.0),
                (4.0, 0.0),
                (4.0, 5.3),
                (2.7, 5.3),
                (1.9, 2.5),
                (0.0, 2.5),
            ),
            top_z_m=10.0,
            inlet_positions_xy_m=((1.5, 1.5),),
        ),
    )

    data = _chute_poly_data(header, observation)
    width = float(np.ptp(data.points[:, 0]))
    depth = float(np.ptp(data.points[:, 1]))
    minimum_z = float(np.min(data.points[:, 2]))
    maximum_z = float(np.max(data.points[:, 2]))

    assert width == pytest.approx(1.59)
    assert depth == pytest.approx(1.06)
    assert minimum_z == pytest.approx(9.046)
    assert maximum_z == pytest.approx(10.53)


def test_camera_effects_are_seeded_and_bounded() -> None:
    source = np.full((20, 30, 3), 128, dtype=np.uint8)

    first = _apply_effects(
        source,
        seed=42,
        noise_standard_deviation=0.02,
        vignette_strength=0.2,
    )
    second = _apply_effects(
        source,
        seed=42,
        noise_standard_deviation=0.02,
        vignette_strength=0.2,
    )

    assert np.array_equal(first, second)
    assert first.dtype == np.uint8
    assert not np.array_equal(first, source)


def test_explicit_renderer_backend_checks_actual_window() -> None:
    config = SyntheticCameraConfig.from_file()
    _validate_render_window(config, "vtkEGLRenderWindow")
    with pytest.raises(RuntimeError, match="unexpected window"):
        _validate_render_window(config, "vtkXOpenGLRenderWindow")
    with pytest.raises(RuntimeError, match="unexpected window"):
        _validate_render_window(
            replace(config, backend="egl"), "vtkOSOpenGLRenderWindow"
        )
