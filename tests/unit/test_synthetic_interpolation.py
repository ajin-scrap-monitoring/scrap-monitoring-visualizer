from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from scrap_monitoring_visualizer.contracts import ContractParser, Observation
from scrap_monitoring_visualizer.synthetic_camera.interpolation import (
    InterpolationError,
    interpolate_observations,
)
from scrap_monitoring_visualizer.synthetic_camera.models import TimingConfig
from scrap_monitoring_visualizer.synthetic_camera.scheduler import (
    materialize_target,
    replay_frames,
    schedule_segment,
)

CONTRACT_ROOT = Path("contracts/observation/v1")


@pytest.fixture(scope="module")
def observation() -> Observation:
    parser = ContractParser(CONTRACT_ROOT)
    line = (
        (CONTRACT_ROOT / "fixtures/observation.v1.jsonl")
        .read_bytes()
        .splitlines(keepends=True)[1]
    )
    parsed = parser.parse_line(line).value
    assert isinstance(parsed, Observation)
    return parsed


def _right(observation: Observation) -> Observation:
    return replace(
        observation,
        sequence=2,
        scenario=replace(
            observation.scenario,
            elapsed_s=2.0,
            surface_updated_at_s=2.0,
            surface_fill_ratio=0.3,
            surface_volume_m3=0.5,
        ),
        surface=replace(
            observation.surface,
            heights_m=((0.2, 0.3), (0.4, 0.5)),
        ),
    )


def test_interpolation_blends_complete_surface_and_continuous_status(
    observation: Observation,
) -> None:
    frame = interpolate_observations(
        observation,
        _right(observation),
        1.5,
        max_gap_s=2.0,
    )

    assert frame.mode == "interpolated"
    assert frame.alpha == pytest.approx(0.5)
    assert frame.left_sequence == 1
    assert frame.right_sequence == 2
    assert frame.observation.sequence == 1
    assert tuple(
        height for row in frame.observation.surface.heights_m for height in row
    ) == pytest.approx((0.1, 0.2, 0.3, 0.4))
    assert frame.observation.scenario.surface_fill_ratio == pytest.approx(0.2)
    assert frame.observation.scenario.surface_volume_m3 == pytest.approx(0.3)


def test_interpolation_switches_discrete_state_only_at_right_endpoint(
    observation: Observation,
) -> None:
    right = _right(observation)
    right = replace(
        right,
        scenario=replace(
            right.scenario,
            cycle_index=1,
            phase="collecting",
            current_inlet_index=None,
        ),
    )

    middle = interpolate_observations(
        observation, right, 1.5, max_gap_s=2.0
    ).observation
    endpoint = interpolate_observations(
        observation, right, 2.0, max_gap_s=2.0
    ).observation

    assert (middle.scenario.cycle_index, middle.scenario.phase) == (0, "filling")
    assert middle.scenario.current_inlet_index == 0
    assert endpoint == right


@pytest.mark.parametrize(
    ("candidate", "code"),
    [
        (lambda value: replace(value, run_id="other"), "run"),
        (lambda value: replace(value, sequence=3), "sequence"),
        (
            lambda value: replace(
                value,
                surface=replace(value.surface, x_coordinates_m=(0.0, 0.5, 1.0)),
            ),
            "grid",
        ),
    ],
)
def test_interpolation_rejects_boundaries(
    observation: Observation, candidate: object, code: str
) -> None:
    right = candidate(_right(observation))  # type: ignore[operator]

    with pytest.raises(InterpolationError) as caught:
        interpolate_observations(observation, right, 1.5, max_gap_s=2.0)

    assert caught.value.code == code


def test_scheduler_emits_thirty_samples_for_one_second(
    observation: Observation,
) -> None:
    frames = schedule_segment(
        observation,
        _right(observation),
        fps=30,
        timing=TimingConfig(max_interpolation_gap_s=2.0, max_segment_frames=60),
    )

    assert len(frames) == 30
    assert frames[0].elapsed_s == pytest.approx(1.0 + 1 / 30)
    assert materialize_target(
        observation,
        _right(observation),
        frames[-1],
        timing=TimingConfig(max_interpolation_gap_s=2.0, max_segment_frames=60),
    ).observation == _right(observation)


def test_scheduler_holds_instead_of_interpolating_a_gap(
    observation: Observation,
) -> None:
    right = replace(_right(observation), sequence=4)

    frames = schedule_segment(
        observation,
        right,
        fps=30,
        timing=TimingConfig(max_interpolation_gap_s=2.0, max_segment_frames=60),
    )

    assert len(frames) == 1
    assert frames[0].mode == "hold"
    assert frames[0].reason == "sequence"
    assert (
        materialize_target(
            observation,
            right,
            frames[0],
            timing=TimingConfig(max_interpolation_gap_s=2.0, max_segment_frames=60),
        ).observation
        == right
    )


def test_scheduler_rejects_oversized_segment_before_materializing_targets(
    observation: Observation,
) -> None:
    right = replace(
        _right(observation),
        scenario=replace(
            _right(observation).scenario,
            elapsed_s=1e308,
            surface_updated_at_s=1e308,
        ),
    )

    frames = schedule_segment(
        observation,
        right,
        fps=60,
        timing=TimingConfig(
            max_interpolation_gap_s=1e308,
            max_segment_frames=3_000,
        ),
    )

    assert len(frames) == 1
    assert frames[0].mode == "hold"
    assert frames[0].reason == "frame_limit"


def test_replay_includes_initial_exact_frame(observation: Observation) -> None:
    frames = tuple(
        replay_frames(
            (observation, _right(observation)),
            fps=2,
            timing=TimingConfig(max_interpolation_gap_s=2.0, max_segment_frames=10),
        )
    )

    assert [frame.observation.scenario.elapsed_s for frame in frames] == [
        1.0,
        1.5,
        2.0,
    ]
