from __future__ import annotations

from collections.abc import Callable

import pytest

from garminconnect_mcp.aerobic_drift import (
    MalformedActivityDetailResponseError,
    analyze_aerobic_drift,
)

CHANNELS = [
    "directTimestamp",
    "sumDistance",
    "directSpeed",
    "directHeartRate",
    "directElevation",
]


def details_from_points(
    points: list[tuple[float, float, float, float, float]],
    *,
    channels: list[str] = CHANNELS,
) -> dict[str, object]:
    indexes = {name: index for index, name in enumerate(CHANNELS)}
    return {
        "metricDescriptors": [
            {"key": name, "metricsIndex": indexes[name], "unit": "synthetic"}
            for name in channels
        ],
        "activityDetailMetrics": [{"metrics": list(point)} for point in points],
    }


def steady_points(
    *,
    count: int = 41,
    interval_s: float = 60,
    speed: float = 3.0,
    heart_rate: Callable[[int], float] = lambda _: 150.0,
    elevation: Callable[[int], float] = lambda _: 10.0,
) -> list[tuple[float, float, float, float, float]]:
    return [
        (
            index * interval_s,
            index * interval_s * speed,
            speed,
            heart_rate(index),
            elevation(index),
        )
        for index in range(count)
    ]


def test_steady_speed_and_hr_has_near_zero_decoupling() -> None:
    result = analyze_aerobic_drift("101", details_from_points(steady_points()))

    assert result["usable_for_drift_analysis"] is True
    assert result["first_half_distance_m"] == result["second_half_distance_m"]
    assert result["first_half_pace_s_per_km"] == pytest.approx(333.33, abs=0.01)
    assert result["heart_rate_change_bpm"] == pytest.approx(0)
    assert result["aerobic_decoupling_pct"] == pytest.approx(0)


def test_steady_speed_and_rising_hr_has_positive_decoupling() -> None:
    points = steady_points(heart_rate=lambda index: 140 + index * 0.5)
    result = analyze_aerobic_drift("102", details_from_points(points))

    assert result["heart_rate_change_bpm"] > 0
    assert result["speed_change_pct"] == pytest.approx(0)
    assert result["aerobic_decoupling_pct"] > 0


def test_faster_second_half_with_proportional_hr_has_near_zero_decoupling() -> None:
    points: list[tuple[float, float, float, float, float]] = []
    timestamp = distance = 0.0
    points.append((timestamp, distance, 3.0, 150.0, 10.0))
    for _ in range(20):
        timestamp += 60
        distance += 180
        points.append((timestamp, distance, 3.0, 150.0, 10.0))
    for _ in range(20):
        duration = 3600 / 20 / 3.3
        timestamp += duration
        distance += 180
        points.append((timestamp, distance, 3.3, 165.0, 10.0))

    result = analyze_aerobic_drift("103", details_from_points(points))

    assert result["speed_change_pct"] == pytest.approx(10, abs=0.1)
    # Trapezoidal HR weighting includes the boundary transition sample.
    assert result["heart_rate_change_pct"] == pytest.approx(10, abs=0.3)
    assert result["aerobic_decoupling_pct"] == pytest.approx(0, abs=0.3)


def test_slower_second_half_reports_positive_pace_change_and_warning() -> None:
    points: list[tuple[float, float, float, float, float]] = []
    timestamp = distance = 0.0
    for index in range(41):
        speed = 3.2 if index <= 20 else 2.5
        if index:
            timestamp += 60
            distance += speed * 60
        points.append((timestamp, distance, speed, 150.0, 10.0))

    result = analyze_aerobic_drift("104", details_from_points(points))

    assert result["pace_change_pct"] > 10
    assert result["aerobic_decoupling_pct"] > 0
    assert result["usable_for_drift_analysis"] is False
    assert any("Half pace difference" in warning for warning in result["warnings"])


def test_irregular_sample_timing_is_time_weighted() -> None:
    timestamps = [0.0]
    intervals = [30, 90, 45, 75] * 10
    for interval in intervals:
        timestamps.append(timestamps[-1] + interval)
    points = [(time, time * 3, 3.0, 150.0, 10.0) for time in timestamps]

    result = analyze_aerobic_drift("105", details_from_points(points))

    assert result["usable_for_drift_analysis"] is True
    assert result["first_half_pace_s_per_km"] == pytest.approx(333.33, abs=0.01)
    assert result["aerobic_decoupling_pct"] == pytest.approx(0)


@pytest.mark.parametrize(
    "missing_channel",
    ["directHeartRate", "directSpeed", "sumDistance", "directTimestamp"],
)
def test_missing_required_channel_returns_unusable(missing_channel: str) -> None:
    channels = [channel for channel in CHANNELS if channel != missing_channel]
    result = analyze_aerobic_drift(
        "106", details_from_points(steady_points(), channels=channels)
    )

    assert result["usable_for_drift_analysis"] is False
    assert result["aerobic_decoupling_pct"] is None
    assert result["warnings"] == [f"Missing required Garmin channel: {missing_channel}"]


@pytest.mark.parametrize("field_index", [2, 3])
@pytest.mark.parametrize("invalid", [0.0, -1.0, float("nan")])
def test_zero_or_invalid_hr_or_speed_is_not_used(
    field_index: int, invalid: float
) -> None:
    points = [list(point) for point in steady_points()]
    for point in points:
        point[field_index] = invalid
    result = analyze_aerobic_drift(
        "107",
        details_from_points([tuple(point) for point in points]),  # type: ignore[arg-type]
    )

    assert result["usable_for_drift_analysis"] is False
    assert result["aerobic_decoupling_pct"] is None


def test_too_few_samples_is_unusable_but_keeps_factual_metrics() -> None:
    result = analyze_aerobic_drift(
        "108", details_from_points(steady_points(count=10, interval_s=180))
    )

    assert result["sample_count"] == 10
    assert result["aerobic_decoupling_pct"] == pytest.approx(0)
    assert result["usable_for_drift_analysis"] is False
    assert any("Too few" in warning for warning in result["warnings"])


def test_major_stop_is_excluded_and_flagged() -> None:
    points = steady_points()
    mutable = [list(point) for point in points]
    stop_distance = mutable[10][1]
    for index in (11, 12, 13):
        mutable[index][1] = stop_distance
        mutable[index][2] = 0.0
    result = analyze_aerobic_drift(
        "109",
        details_from_points([tuple(point) for point in mutable]),  # type: ignore[arg-type]
    )

    assert result["usable_for_drift_analysis"] is False
    assert any("stopped time" in warning for warning in result["warnings"])


def test_interval_laps_and_walking_sections_are_flagged() -> None:
    result = analyze_aerobic_drift(
        "110",
        details_from_points(steady_points()),
        recorded_laps={"lapDTOs": [{"intensityType": "INTERVAL"}]},
        typed_splits={"splits": [{"type": "RWD_WALK", "duration": 180}]},
    )

    assert result["usable_for_drift_analysis"] is False
    assert any("Interval-like" in warning for warning in result["warnings"])
    assert any("walking or standing" in warning for warning in result["warnings"])


def test_strongly_uneven_elevation_is_flagged() -> None:
    points = steady_points(elevation=lambda index: 10 + (index % 10) * 10)
    result = analyze_aerobic_drift("111", details_from_points(points))

    assert result["usable_for_drift_analysis"] is False
    assert any("elevation profile" in warning for warning in result["warnings"])


@pytest.mark.parametrize(
    "raw",
    [None, {}, {"metricDescriptors": [], "activityDetailMetrics": []}],
)
def test_malformed_detail_response_is_rejected(raw: object) -> None:
    with pytest.raises(MalformedActivityDetailResponseError, match="activity-detail"):
        analyze_aerobic_drift("112", raw)
