from __future__ import annotations

import math
from datetime import date
from typing import Any, TypedDict


class NormalizedActivity(TypedDict):
    """Compact, stable activity representation with explicit units."""

    activity_id: str | None
    start_time_local: str | None
    start_time_gmt: str | None
    activity_type: str | None
    name: str | None
    distance_m: float | None
    duration_s: float | None
    pace_s_per_km: float | None
    average_heart_rate_bpm: float | None
    maximum_heart_rate_bpm: float | None
    average_cadence_spm: float | None
    elevation_gain_m: float | None


class ActivitySplit(TypedDict):
    """One Garmin-recorded lap with explicit public units."""

    split_index: int
    start_time_local: str | None
    distance_m: float | None
    duration_s: float | None
    moving_duration_s: float | None
    elapsed_duration_s: float | None
    pace_s_per_km: float | None
    average_heart_rate_bpm: float | None
    maximum_heart_rate_bpm: float | None
    average_cadence_spm: float | None
    elevation_gain_m: float | None
    elevation_loss_m: float | None
    intensity_type: str | None


class NormalizedActivitySplits(TypedDict):
    activity_id: str
    split_type: str
    splits: list[ActivitySplit]


class MalformedActivityResponseError(RuntimeError):
    """Raised when Garmin returns an unexpected activity response shape."""


_KNOWN_ACTIVITY_KEYS = {
    "activityId",
    "activityName",
    "activityType",
    "activityTypeDTO",
    "averageHR",
    "distance",
    "duration",
    "startTimeGMT",
    "startTimeLocal",
    "summaryDTO",
}


def _first_present(data: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        value = data.get(key)
        if value is not None:
            return value
    return None


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    result = float(value)
    return result if math.isfinite(result) else None


def _text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    value = value.strip()
    return value or None


def _layers(raw: dict[str, Any]) -> tuple[dict[str, Any], ...]:
    layers: list[dict[str, Any]] = [raw]
    for key in ("summaryDTO", "activitySummary", "summary"):
        nested = raw.get(key)
        if isinstance(nested, dict):
            layers.append(nested)
    return tuple(layers)


def _from_layers(layers: tuple[dict[str, Any], ...], keys: tuple[str, ...]) -> Any:
    for layer in layers:
        value = _first_present(layer, keys)
        if value is not None:
            return value
    return None


def _activity_type(value: Any) -> str | None:
    if isinstance(value, dict):
        value = _first_present(value, ("typeKey", "activityTypeKey", "key"))
    return _text(value)


def _pace_from_speed(speed_m_per_s: Any) -> float | None:
    speed = _number(speed_m_per_s)
    if speed is None or speed <= 0:
        return None
    return round(1000 / speed, 2)


def normalize_activity(raw: Any) -> NormalizedActivity:
    """Normalize one Garmin activity without retaining its raw response."""
    if not isinstance(raw, dict) or not raw:
        raise MalformedActivityResponseError(
            "Garmin returned a malformed activity response"
        )

    layers = _layers(raw)
    if not any(_KNOWN_ACTIVITY_KEYS.intersection(layer) for layer in layers):
        raise MalformedActivityResponseError(
            "Garmin returned an unrecognized activity response"
        )

    raw_id = _from_layers(layers, ("activityId", "activity_id", "id"))
    activity_id = (
        str(raw_id)
        if not isinstance(raw_id, bool) and isinstance(raw_id, int | str)
        else None
    )
    activity_type = _activity_type(
        _from_layers(
            layers,
            ("activityType", "activityTypeDTO", "sportType", "activity_type"),
        )
    )

    return {
        "activity_id": activity_id,
        "start_time_local": _text(
            _from_layers(layers, ("startTimeLocal", "startTime", "start_time_local"))
        ),
        "start_time_gmt": _text(
            _from_layers(layers, ("startTimeGMT", "startTimeGmt", "start_time_gmt"))
        ),
        "activity_type": activity_type,
        "name": _text(_from_layers(layers, ("activityName", "name", "activity_name"))),
        "distance_m": _number(
            _from_layers(layers, ("distance", "distanceMeters", "distance_m"))
        ),
        "duration_s": _number(
            _from_layers(layers, ("duration", "durationSeconds", "duration_s"))
        ),
        "pace_s_per_km": _pace_from_speed(
            _from_layers(layers, ("averageSpeed", "avgSpeed", "average_speed"))
        ),
        "average_heart_rate_bpm": _number(
            _from_layers(layers, ("averageHR", "averageHeartRate", "avgHR"))
        ),
        "maximum_heart_rate_bpm": _number(
            _from_layers(layers, ("maxHR", "maximumHeartRate", "maxHeartRate"))
        ),
        "average_cadence_spm": _number(
            _from_layers(
                layers,
                (
                    "averageRunningCadenceInStepsPerMinute",
                    "averageRunCadence",
                    "averageCadence",
                ),
            )
        ),
        "elevation_gain_m": _number(
            _from_layers(layers, ("elevationGain", "gainElevation"))
        ),
    }


def _positive_number(value: Any) -> float | None:
    number = _number(value)
    return number if number is not None and number > 0 else None


def normalize_activity_splits(
    raw: Any, *, activity_id: str
) -> NormalizedActivitySplits:
    """Normalize Garmin-recorded laps without retaining their raw payloads.

    Pace is derived only from Garmin's supplied ``averageMovingSpeed`` in
    meters per second. It is not reconstructed from lap distance and duration.
    """
    if not isinstance(raw, dict) or not raw:
        raise MalformedActivityResponseError(
            "Garmin returned a malformed activity-splits response"
        )
    raw_laps = raw.get("lapDTOs")
    if not isinstance(raw_laps, list) or not raw_laps:
        raise MalformedActivityResponseError(
            "Garmin returned no recorded activity laps"
        )
    if any(not isinstance(lap, dict) for lap in raw_laps):
        raise MalformedActivityResponseError(
            "Garmin returned malformed recorded activity laps"
        )

    splits: list[ActivitySplit] = []
    for position, lap in enumerate(raw_laps, start=1):
        raw_index = lap.get("lapIndex")
        split_index = (
            raw_index
            if isinstance(raw_index, int)
            and not isinstance(raw_index, bool)
            and raw_index > 0
            else position
        )
        splits.append(
            {
                "split_index": split_index,
                "start_time_local": _text(lap.get("startTimeLocal")),
                "distance_m": _number(lap.get("distance")),
                "duration_s": _number(lap.get("duration")),
                "moving_duration_s": _number(lap.get("movingDuration")),
                "elapsed_duration_s": _number(lap.get("elapsedDuration")),
                "pace_s_per_km": _pace_from_speed(
                    _positive_number(lap.get("averageMovingSpeed"))
                ),
                "average_heart_rate_bpm": _number(lap.get("averageHR")),
                "maximum_heart_rate_bpm": _number(lap.get("maxHR")),
                "average_cadence_spm": _number(lap.get("averageRunCadence")),
                "elevation_gain_m": _number(lap.get("elevationGain")),
                "elevation_loss_m": _number(lap.get("elevationLoss")),
                "intensity_type": _text(lap.get("intensityType")),
            }
        )

    return {"activity_id": activity_id, "split_type": "lap", "splits": splits}


def activity_is_running(activity: NormalizedActivity) -> bool:
    activity_type = activity["activity_type"]
    return activity_type is not None and "run" in activity_type.casefold()


def normalized_activity_date(activity: NormalizedActivity) -> date | None:
    """Return the local activity date, falling back to GMT when usable."""
    for value in (activity["start_time_local"], activity["start_time_gmt"]):
        if value is None or len(value) < 10:
            continue
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            continue
    return None


def activity_items(raw: Any) -> list[dict[str, Any]]:
    """Extract a Garmin activity list from only the supported response envelopes."""
    items: Any = raw
    if isinstance(raw, dict):
        items = _first_present(raw, ("activities", "activityList", "items"))

    if not isinstance(items, list) or any(not isinstance(item, dict) for item in items):
        raise MalformedActivityResponseError(
            "Garmin returned a malformed recent-activities response"
        )
    return items
