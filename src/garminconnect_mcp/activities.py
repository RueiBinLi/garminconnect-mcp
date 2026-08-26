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
