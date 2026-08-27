from __future__ import annotations

import math
from datetime import datetime
from typing import Any, TypedDict

from garminconnect.activity_details import parse_activity_detail_metrics


class ActivityTemperatureSummary(TypedDict):
    """Compact activity/device-recorded temperature summary in Celsius."""

    activity_id: str
    average_temperature_c: float | None
    minimum_temperature_c: float | None
    maximum_temperature_c: float | None
    sample_count: int
    source: str
    warnings: list[str]


class ActivityWeatherObservation(TypedDict):
    """Historical weather-station observation associated with an activity."""

    activity_id: str
    observed_at: str | None
    temperature: float | None
    apparent_temperature: float | None
    dew_point: float | None
    relative_humidity_pct: float | None
    wind_speed: float | None
    wind_gust: float | None
    wind_direction: float | None
    wind_direction_compass_point: str | None
    weather_condition: str | None
    weather_condition_id: str | None
    weather_station_present: bool
    weather_station_timezone: str | None
    source: str
    units_verified: bool


class MalformedActivityTemperatureResponseError(RuntimeError):
    """Raised when Garmin activity-detail temperature data is malformed."""


class MalformedActivityWeatherResponseError(RuntimeError):
    """Raised when Garmin activity weather has an unsupported top-level shape."""


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    result = float(value)
    return result if math.isfinite(result) else None


def _text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    result = value.strip()
    return result or None


def _identifier(value: Any) -> str | None:
    if isinstance(value, bool) or not isinstance(value, int | str):
        return None
    return _text(str(value))


def _validate_activity_details(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict) or not raw:
        raise MalformedActivityTemperatureResponseError(
            "Garmin returned a malformed activity-temperature response"
        )

    descriptors = raw.get("metricDescriptors")
    samples = raw.get("activityDetailMetrics")
    if not isinstance(descriptors, list) or not isinstance(samples, list):
        raise MalformedActivityTemperatureResponseError(
            "Garmin returned malformed activity-temperature channels"
        )
    if any(not isinstance(descriptor, dict) for descriptor in descriptors):
        raise MalformedActivityTemperatureResponseError(
            "Garmin returned malformed activity-temperature descriptors"
        )
    if any(not isinstance(sample, dict) for sample in samples):
        raise MalformedActivityTemperatureResponseError(
            "Garmin returned malformed activity-temperature samples"
        )
    if any(not isinstance(sample.get("metrics"), list) for sample in samples):
        raise MalformedActivityTemperatureResponseError(
            "Garmin returned malformed activity-temperature sample metrics"
        )
    return raw


def normalize_activity_temperature(
    raw: Any, *, activity_id: str
) -> ActivityTemperatureSummary:
    """Summarize valid ``directAirTemperature`` samples arithmetically.

    Garmin metric positions are resolved through the installed client's parser;
    no fixed positional index is used. Invalid and unavailable samples are ignored.
    """
    details = _validate_activity_details(raw)
    parsed = parse_activity_detail_metrics(details)
    values: list[float] = []
    discarded = 0

    for sample in parsed:
        if "directAirTemperature" not in sample:
            continue
        value = _number(sample["directAirTemperature"])
        if value is None:
            discarded += 1
            continue
        values.append(value)

    warnings: list[str] = []
    if not values:
        warnings.append(
            "Garmin activity details contained no valid directAirTemperature samples"
        )
    elif discarded:
        warnings.append(f"Ignored {discarded} invalid directAirTemperature samples")

    return {
        "activity_id": activity_id,
        "average_temperature_c": math.fsum(values) / len(values) if values else None,
        "minimum_temperature_c": min(values) if values else None,
        "maximum_temperature_c": max(values) if values else None,
        "sample_count": len(values),
        "source": "garmin_activity_detail_directAirTemperature",
        "warnings": warnings,
    }


def _iso_datetime_with_offset(value: Any) -> str | None:
    text = _text(value)
    if text is None:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return text if parsed.tzinfo is not None else None


def normalize_activity_weather(
    raw: Any, *, activity_id: str
) -> ActivityWeatherObservation:
    """Normalize a historical Garmin weather-station observation.

    Temperature and wind units are intentionally left unqualified because the
    unofficial endpoint's unit semantics have not been verified.
    """
    if not isinstance(raw, dict):
        raise MalformedActivityWeatherResponseError(
            "Garmin returned a malformed activity-weather response"
        )

    weather_type = raw.get("weatherTypeDTO")
    if not isinstance(weather_type, dict):
        weather_type = {}
    weather_station = raw.get("weatherStationDTO")
    station_present = isinstance(weather_station, dict) and bool(weather_station)
    if not station_present:
        weather_station = {}

    return {
        "activity_id": activity_id,
        "observed_at": _iso_datetime_with_offset(raw.get("issueDate")),
        "temperature": _number(raw.get("temp")),
        "apparent_temperature": _number(raw.get("apparentTemp")),
        "dew_point": _number(raw.get("dewPoint")),
        "relative_humidity_pct": _number(raw.get("relativeHumidity")),
        "wind_speed": _number(raw.get("windSpeed")),
        "wind_gust": _number(raw.get("windGust")),
        "wind_direction": _number(raw.get("windDirection")),
        "wind_direction_compass_point": _text(raw.get("windDirectionCompassPoint")),
        "weather_condition": _text(weather_type.get("desc")),
        "weather_condition_id": _identifier(weather_type.get("weatherTypePk")),
        "weather_station_present": station_present,
        "weather_station_timezone": _text(weather_station.get("timezone")),
        "source": "garmin_activity_weather_station",
        "units_verified": False,
    }
