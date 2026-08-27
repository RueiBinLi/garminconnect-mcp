from __future__ import annotations

from typing import Any, TypedDict


class HeartRateZone(TypedDict):
    zone: int
    minimum_heart_rate_bpm: int
    maximum_heart_rate_bpm: int


class NormalizedHeartRateZones(TypedDict):
    sport: str
    source_sport: str
    training_method: str | None
    maximum_heart_rate_bpm: int
    resting_heart_rate_bpm: int | None
    lactate_threshold_heart_rate_bpm: int | None
    zones: list[HeartRateZone]


class MalformedHeartRateZoneResponseError(RuntimeError):
    """Raised when Garmin returns an unsupported heart-rate-zone shape."""


def _optional_bpm(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value if 20 <= value <= 250 else None


def _required_bpm(value: Any) -> int:
    normalized = _optional_bpm(value)
    if normalized is None:
        raise MalformedHeartRateZoneResponseError(
            "Garmin returned malformed heart-rate-zone boundaries"
        )
    return normalized


def normalize_running_heart_rate_zones(raw: Any) -> NormalizedHeartRateZones:
    """Select running/default floors and return five contiguous bpm ranges."""
    if (
        not isinstance(raw, list)
        or not raw
        or any(not isinstance(item, dict) for item in raw)
    ):
        raise MalformedHeartRateZoneResponseError(
            "Garmin returned a malformed heart-rate-zone response"
        )
    candidates = [
        item
        for item in raw
        if isinstance(item.get("sport"), str)
        and item["sport"].casefold() in {"running", "default"}
    ]
    running = next(
        (item for item in candidates if item["sport"].casefold() == "running"),
        None,
    )
    selected = running or next(
        (item for item in candidates if item["sport"].casefold() == "default"),
        None,
    )
    if selected is None:
        raise MalformedHeartRateZoneResponseError(
            "Garmin did not return running or default heart-rate zones"
        )

    floors = [_required_bpm(selected.get(f"zone{zone}Floor")) for zone in range(1, 6)]
    maximum = _required_bpm(selected.get("maxHeartRateUsed"))
    if floors != sorted(set(floors)) or floors[-1] >= maximum:
        raise MalformedHeartRateZoneResponseError(
            "Garmin returned malformed heart-rate-zone boundaries"
        )
    zones: list[HeartRateZone] = []
    for index, floor in enumerate(floors):
        ceiling = floors[index + 1] - 1 if index < 4 else maximum
        if floor >= ceiling:
            raise MalformedHeartRateZoneResponseError(
                "Garmin returned malformed heart-rate-zone boundaries"
            )
        zones.append(
            {
                "zone": index + 1,
                "minimum_heart_rate_bpm": floor,
                "maximum_heart_rate_bpm": ceiling,
            }
        )

    method = selected.get("trainingMethod")
    return {
        "sport": "running",
        "source_sport": selected["sport"].casefold(),
        "training_method": method if isinstance(method, str) and method else None,
        "maximum_heart_rate_bpm": maximum,
        "resting_heart_rate_bpm": _optional_bpm(selected.get("restingHeartRateUsed")),
        "lactate_threshold_heart_rate_bpm": _optional_bpm(
            selected.get("lactateThresholdHeartRateUsed")
        ),
        "zones": zones,
    }
