from __future__ import annotations

import math
from typing import Any, TypedDict

from garminconnect.activity_details import parse_activity_detail_metrics

MIN_ANALYSIS_DURATION_S = 1200.0
MIN_ANALYSIS_DISTANCE_M = 3000.0
MIN_VALID_SAMPLE_COUNT = 20
STOP_SPEED_M_PER_S = 0.5
MAJOR_STOP_DURATION_S = 60.0
MAJOR_STOP_FRACTION = 0.05
LARGE_HALF_PACE_DIFFERENCE_PCT = 10.0
STRONG_ELEVATION_RANGE_M = 60.0
STRONG_ELEVATION_GAIN_M_PER_KM = 20.0


class AerobicDriftSummary(TypedDict):
    activity_id: str
    method: str
    usable_for_drift_analysis: bool
    first_half_distance_m: float | None
    first_half_duration_s: float | None
    first_half_pace_s_per_km: float | None
    first_half_average_hr_bpm: float | None
    second_half_distance_m: float | None
    second_half_duration_s: float | None
    second_half_pace_s_per_km: float | None
    second_half_average_hr_bpm: float | None
    heart_rate_change_bpm: float | None
    heart_rate_change_pct: float | None
    speed_change_pct: float | None
    pace_change_pct: float | None
    aerobic_decoupling_pct: float | None
    sample_count: int
    warnings: list[str]


class MalformedActivityDetailResponseError(RuntimeError):
    """Raised when Garmin activity-detail data has an unknown envelope."""


class _Half(TypedDict):
    distance_m: float
    duration_s: float
    heart_rate_integral: float


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    result = float(value)
    return result if math.isfinite(result) else None


def _positive(value: Any) -> float | None:
    result = _number(value)
    return result if result is not None and result > 0 else None


def _timestamp_s(value: Any) -> float | None:
    result = _number(value)
    if result is None:
        return None
    # Garmin normally supplies Unix milliseconds; accepting seconds also keeps
    # the pure analyzer useful for synthetic inputs and alternate devices.
    return result / 1000.0 if abs(result) >= 100_000_000_000 else result


def _rounded(value: float | None) -> float | None:
    return None if value is None else round(value, 2)


def _percent_change(first: float | None, second: float | None) -> float | None:
    if first is None or second is None or first == 0:
        return None
    return round((second - first) / first * 100, 2)


def _empty_summary(
    activity_id: str, *, sample_count: int, warnings: list[str]
) -> AerobicDriftSummary:
    return {
        "activity_id": activity_id,
        "method": "distance_halves_time_weighted_speed_hr_efficiency",
        "usable_for_drift_analysis": False,
        "first_half_distance_m": None,
        "first_half_duration_s": None,
        "first_half_pace_s_per_km": None,
        "first_half_average_hr_bpm": None,
        "second_half_distance_m": None,
        "second_half_duration_s": None,
        "second_half_pace_s_per_km": None,
        "second_half_average_hr_bpm": None,
        "heart_rate_change_bpm": None,
        "heart_rate_change_pct": None,
        "speed_change_pct": None,
        "pace_change_pct": None,
        "aerobic_decoupling_pct": None,
        "sample_count": sample_count,
        "warnings": warnings,
    }


def _descriptor_names(details: dict[str, Any]) -> set[str]:
    descriptors = details.get("metricDescriptors")
    if not isinstance(descriptors, list) or not descriptors:
        raise MalformedActivityDetailResponseError(
            "Garmin returned malformed activity-detail descriptors"
        )
    if any(not isinstance(item, dict) for item in descriptors):
        raise MalformedActivityDetailResponseError(
            "Garmin returned malformed activity-detail descriptors"
        )
    return {
        key
        for descriptor in descriptors
        if isinstance((key := descriptor.get("key")), str)
    }


def _evidence_duration(raw: Any, type_fragments: tuple[str, ...]) -> float:
    if not isinstance(raw, dict):
        return 0.0
    items = raw.get("splits")
    if not isinstance(items, list):
        return 0.0
    total = 0.0
    for item in items:
        if not isinstance(item, dict):
            continue
        split_type = str(item.get("type") or "").upper()
        duration = _positive(item.get("duration"))
        if duration is not None and any(part in split_type for part in type_fragments):
            total += duration
    return total


def _has_interval_laps(raw: Any) -> bool:
    if not isinstance(raw, dict):
        return False
    laps = raw.get("lapDTOs")
    if not isinstance(laps, list):
        return False
    interval_terms = ("INTERVAL", "RECOVERY", "REST", "WARMUP", "COOLDOWN")
    return any(
        isinstance(lap, dict)
        and any(
            term in str(lap.get("intensityType") or "").upper()
            for term in interval_terms
        )
        for lap in laps
    )


def _add_piece(
    half: _Half,
    *,
    distance_m: float,
    duration_s: float,
    start_hr: float,
    end_hr: float,
    start_fraction: float,
    end_fraction: float,
) -> None:
    piece_start_hr = start_hr + (end_hr - start_hr) * start_fraction
    piece_end_hr = start_hr + (end_hr - start_hr) * end_fraction
    half["distance_m"] += distance_m
    half["duration_s"] += duration_s
    half["heart_rate_integral"] += (piece_start_hr + piece_end_hr) / 2 * duration_s


def analyze_aerobic_drift(
    activity_id: str,
    details: Any,
    *,
    recorded_laps: Any = None,
    typed_splits: Any = None,
) -> AerobicDriftSummary:
    """Calculate factual speed/HR decoupling over equal distance halves.

    Consecutive samples form time-weighted segments. Stationary segments are
    excluded from the two running halves but retained as validity evidence.
    Garmin may downsample the input before this function receives it.
    """
    if not isinstance(details, dict) or not details:
        raise MalformedActivityDetailResponseError(
            "Garmin returned a malformed activity-detail response"
        )
    metrics = details.get("activityDetailMetrics")
    if not isinstance(metrics, list):
        raise MalformedActivityDetailResponseError(
            "Garmin returned malformed activity-detail samples"
        )

    descriptor_names = _descriptor_names(details)
    required = {
        "directHeartRate",
        "directSpeed",
        "sumDistance",
        "directTimestamp",
    }
    missing = sorted(required - descriptor_names)
    if missing:
        return _empty_summary(
            activity_id,
            sample_count=0,
            warnings=[f"Missing required Garmin channel: {name}" for name in missing],
        )

    parsed = parse_activity_detail_metrics(details)
    samples: list[dict[str, float]] = []
    for sample in parsed:
        timestamp = _timestamp_s(sample.get("directTimestamp"))
        distance = _number(sample.get("sumDistance"))
        speed = _number(sample.get("directSpeed"))
        heart_rate = _positive(sample.get("directHeartRate"))
        if (
            timestamp is None
            or distance is None
            or distance < 0
            or speed is None
            or speed < 0
            or heart_rate is None
        ):
            continue
        normalized = {
            "timestamp_s": timestamp,
            "distance_m": distance,
            "speed_m_per_s": speed,
            "heart_rate_bpm": heart_rate,
        }
        elevation = _number(sample.get("directElevation"))
        if elevation is not None:
            normalized["elevation_m"] = elevation
        samples.append(normalized)

    warnings: list[str] = []
    if len(samples) < MIN_VALID_SAMPLE_COUNT:
        warnings.append(
            f"Too few valid samples; at least {MIN_VALID_SAMPLE_COUNT} are required"
        )
    if len(samples) < len(parsed):
        warnings.append("Some Garmin samples lacked valid HR, speed, distance, or time")
    if len(samples) < 2:
        return _empty_summary(activity_id, sample_count=len(samples), warnings=warnings)

    segments: list[dict[str, float]] = []
    stopped_duration_s = 0.0
    elapsed_duration_s = 0.0
    elevation_values: list[float] = []
    elevation_gain_m = 0.0
    previous_elevation: float | None = None
    for first, second in zip(samples, samples[1:], strict=False):
        duration = second["timestamp_s"] - first["timestamp_s"]
        distance = second["distance_m"] - first["distance_m"]
        if duration <= 0 or distance < 0:
            continue
        elapsed_duration_s += duration
        observed_speed = distance / duration
        supplied_speed = (first["speed_m_per_s"] + second["speed_m_per_s"]) / 2
        if observed_speed < STOP_SPEED_M_PER_S or supplied_speed < STOP_SPEED_M_PER_S:
            stopped_duration_s += duration
            continue
        if distance == 0:
            continue
        segments.append(
            {
                "distance_m": distance,
                "duration_s": duration,
                "start_hr": first["heart_rate_bpm"],
                "end_hr": second["heart_rate_bpm"],
            }
        )
        for point in (first, second):
            elevation = point.get("elevation_m")
            if elevation is None:
                continue
            elevation_values.append(elevation)
            if previous_elevation is not None and elevation > previous_elevation:
                elevation_gain_m += elevation - previous_elevation
            previous_elevation = elevation

    total_distance_m = sum(segment["distance_m"] for segment in segments)
    total_duration_s = sum(segment["duration_s"] for segment in segments)
    if total_distance_m < MIN_ANALYSIS_DISTANCE_M:
        warnings.append(
            f"Usable running distance is below {int(MIN_ANALYSIS_DISTANCE_M)} m"
        )
    if total_duration_s < MIN_ANALYSIS_DURATION_S:
        warnings.append(
            f"Usable running duration is below {int(MIN_ANALYSIS_DURATION_S)} s"
        )
    if (
        elapsed_duration_s > 0
        and stopped_duration_s >= MAJOR_STOP_DURATION_S
        and stopped_duration_s / elapsed_duration_s >= MAJOR_STOP_FRACTION
    ):
        warnings.append(
            "Substantial stopped time makes drift interpretation unreliable"
        )

    walking_standing_s = _evidence_duration(typed_splits, ("WALK", "STAND"))
    if walking_standing_s >= MAJOR_STOP_DURATION_S and (
        elapsed_duration_s <= 0
        or walking_standing_s / elapsed_duration_s >= MAJOR_STOP_FRACTION
    ):
        warnings.append("Substantial walking or standing sections were recorded")
    if _has_interval_laps(recorded_laps):
        warnings.append(
            "Interval-like recorded laps make drift interpretation unreliable"
        )

    if not segments or total_distance_m <= 0:
        return _empty_summary(activity_id, sample_count=len(samples), warnings=warnings)

    halfway_m = total_distance_m / 2
    halves: list[_Half] = [
        {"distance_m": 0.0, "duration_s": 0.0, "heart_rate_integral": 0.0},
        {"distance_m": 0.0, "duration_s": 0.0, "heart_rate_integral": 0.0},
    ]
    cumulative_m = 0.0
    for segment in segments:
        segment_start_m = cumulative_m
        segment_end_m = cumulative_m + segment["distance_m"]
        boundaries = [segment_start_m]
        if segment_start_m < halfway_m < segment_end_m:
            boundaries.append(halfway_m)
        boundaries.append(segment_end_m)
        for start_m, end_m in zip(boundaries, boundaries[1:], strict=False):
            fraction_start = (start_m - segment_start_m) / segment["distance_m"]
            fraction_end = (end_m - segment_start_m) / segment["distance_m"]
            fraction = fraction_end - fraction_start
            half_index = 0 if end_m <= halfway_m else 1
            _add_piece(
                halves[half_index],
                distance_m=end_m - start_m,
                duration_s=segment["duration_s"] * fraction,
                start_hr=segment["start_hr"],
                end_hr=segment["end_hr"],
                start_fraction=fraction_start,
                end_fraction=fraction_end,
            )
        cumulative_m = segment_end_m

    def half_metrics(half: _Half) -> tuple[float | None, float | None, float | None]:
        if half["duration_s"] <= 0 or half["distance_m"] <= 0:
            return None, None, None
        speed = half["distance_m"] / half["duration_s"]
        pace = 1000 / speed
        heart_rate = half["heart_rate_integral"] / half["duration_s"]
        return speed, pace, heart_rate

    first_speed, first_pace, first_hr = half_metrics(halves[0])
    second_speed, second_pace, second_hr = half_metrics(halves[1])
    pace_change_pct = _percent_change(first_pace, second_pace)
    if (
        pace_change_pct is not None
        and abs(pace_change_pct) > LARGE_HALF_PACE_DIFFERENCE_PCT
    ):
        warnings.append(
            "Half pace difference exceeds 10%; steady-effort drift is unreliable"
        )

    if elevation_values and total_distance_m > 0:
        elevation_range_m = max(elevation_values) - min(elevation_values)
        gain_per_km = elevation_gain_m / (total_distance_m / 1000)
        if (
            elevation_range_m >= STRONG_ELEVATION_RANGE_M
            and gain_per_km >= STRONG_ELEVATION_GAIN_M_PER_KM
        ):
            warnings.append("Strongly uneven elevation profile makes drift unreliable")

    first_efficiency = (
        first_speed / first_hr
        if first_speed is not None and first_hr is not None and first_hr > 0
        else None
    )
    second_efficiency = (
        second_speed / second_hr
        if second_speed is not None and second_hr is not None and second_hr > 0
        else None
    )
    decoupling = (
        (first_efficiency - second_efficiency) / first_efficiency * 100
        if first_efficiency is not None
        and second_efficiency is not None
        and first_efficiency > 0
        else None
    )

    return {
        "activity_id": activity_id,
        "method": "distance_halves_time_weighted_speed_hr_efficiency",
        "usable_for_drift_analysis": not warnings,
        "first_half_distance_m": _rounded(halves[0]["distance_m"]),
        "first_half_duration_s": _rounded(halves[0]["duration_s"]),
        "first_half_pace_s_per_km": _rounded(first_pace),
        "first_half_average_hr_bpm": _rounded(first_hr),
        "second_half_distance_m": _rounded(halves[1]["distance_m"]),
        "second_half_duration_s": _rounded(halves[1]["duration_s"]),
        "second_half_pace_s_per_km": _rounded(second_pace),
        "second_half_average_hr_bpm": _rounded(second_hr),
        "heart_rate_change_bpm": _rounded(
            second_hr - first_hr
            if first_hr is not None and second_hr is not None
            else None
        ),
        "heart_rate_change_pct": _percent_change(first_hr, second_hr),
        "speed_change_pct": _percent_change(first_speed, second_speed),
        "pace_change_pct": pace_change_pct,
        "aerobic_decoupling_pct": _rounded(decoupling),
        "sample_count": len(samples),
        "warnings": warnings,
    }
