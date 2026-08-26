from __future__ import annotations

import math
import re
from datetime import UTC, date, datetime
from typing import Any, TypedDict


class MalformedRecoveryResponseError(RuntimeError):
    """Raised when Garmin returns an unexpected recovery response shape."""


class NormalizedDailyStatistics(TypedDict):
    date: str
    steps_count: int | None
    step_goal_count: int | None
    distance_m: float | None
    total_energy_kcal: float | None
    active_energy_kcal: float | None
    resting_energy_kcal: float | None
    active_duration_s: float | None
    highly_active_duration_s: float | None
    sedentary_duration_s: float | None
    sleeping_duration_s: float | None
    moderate_intensity_duration_s: float | None
    vigorous_intensity_duration_s: float | None
    resting_heart_rate_bpm: float | None
    minimum_heart_rate_bpm: float | None
    maximum_heart_rate_bpm: float | None
    average_stress_native: float | None
    maximum_stress_native: float | None
    body_battery_charged_native: float | None
    body_battery_drained_native: float | None
    body_battery_highest_native: float | None
    body_battery_lowest_native: float | None


class NormalizedHeartRate(TypedDict):
    date: str
    resting_heart_rate_bpm: float | None
    minimum_heart_rate_bpm: float | None
    maximum_heart_rate_bpm: float | None
    last_seven_days_average_resting_heart_rate_bpm: float | None


class NormalizedSleep(TypedDict):
    date: str
    sleep_start_time_utc: str | None
    sleep_end_time_utc: str | None
    total_sleep_duration_s: float | None
    deep_sleep_duration_s: float | None
    light_sleep_duration_s: float | None
    rem_sleep_duration_s: float | None
    awake_duration_s: float | None
    unmeasurable_duration_s: float | None
    nap_duration_s: float | None
    sleep_score: float | None
    sleep_score_status: str | None
    sleep_window_status: str | None


class NormalizedHRV(TypedDict):
    date: str
    weekly_average_ms: float | None
    last_night_average_ms: float | None
    last_night_five_minute_high_ms: float | None
    status: str | None


class NormalizedBodyBattery(TypedDict):
    date: str
    charged_native: float | None
    drained_native: float | None
    highest_native: float | None
    lowest_native: float | None
    latest_native: float | None


class NormalizedStress(TypedDict):
    date: str
    average_stress_native: float | None
    maximum_stress_native: float | None


_DATE_PATTERN = re.compile(r"\d{4}-\d{2}-\d{2}")


def validate_date(value: Any, *, name: str = "date") -> str:
    """Return a strict YYYY-MM-DD date or raise a secret-safe request error."""
    if not isinstance(value, str) or _DATE_PATTERN.fullmatch(value) is None:
        raise ValueError(f"{name} must use YYYY-MM-DD format")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{name} must be a valid YYYY-MM-DD date") from exc
    if parsed.isoformat() != value:
        raise ValueError(f"{name} must use YYYY-MM-DD format")
    return value


def _object_or_missing(raw: Any, *, operation: str) -> dict[str, Any] | None:
    if raw is None or raw == {}:
        return None
    if not isinstance(raw, dict):
        raise MalformedRecoveryResponseError(
            f"Garmin returned a malformed {operation} response"
        )
    return raw


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    result = float(value)
    return result if math.isfinite(result) else None


def _integer(value: Any) -> int | None:
    number = _number(value)
    return int(number) if number is not None and number.is_integer() else None


def _text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    result = value.strip()
    return result or None


def _minutes_to_seconds(value: Any) -> float | None:
    minutes = _number(value)
    return minutes * 60 if minutes is not None else None


def _timestamp_utc(value: Any) -> str | None:
    numeric = _number(value)
    if numeric is not None:
        seconds = numeric / 1000 if abs(numeric) >= 10_000_000_000 else numeric
        try:
            return (
                datetime.fromtimestamp(seconds, tz=UTC)
                .isoformat()
                .replace("+00:00", "Z")
            )
        except (OverflowError, OSError, ValueError):
            return None

    text = _text(value)
    if text is None:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC).isoformat().replace("+00:00", "Z")


def normalize_daily_statistics(
    raw: Any, requested_date: str
) -> NormalizedDailyStatistics:
    requested_date = validate_date(requested_date)
    data = _object_or_missing(raw, operation="daily-statistics")
    if data is not None and not {
        "calendarDate",
        "totalSteps",
        "restingHeartRate",
        "sleepingSeconds",
    }.intersection(data):
        raise MalformedRecoveryResponseError(
            "Garmin returned an unrecognized daily-statistics response"
        )
    data = data or {}
    return {
        "date": requested_date,
        "steps_count": _integer(data.get("totalSteps")),
        "step_goal_count": _integer(data.get("dailyStepGoal")),
        "distance_m": _number(data.get("totalDistanceMeters")),
        "total_energy_kcal": _number(data.get("totalKilocalories")),
        "active_energy_kcal": _number(data.get("activeKilocalories")),
        "resting_energy_kcal": _number(data.get("bmrKilocalories")),
        "active_duration_s": _number(data.get("activeSeconds")),
        "highly_active_duration_s": _number(data.get("highlyActiveSeconds")),
        "sedentary_duration_s": _number(data.get("sedentarySeconds")),
        "sleeping_duration_s": _number(data.get("sleepingSeconds")),
        "moderate_intensity_duration_s": _minutes_to_seconds(
            data.get("moderateIntensityMinutes")
        ),
        "vigorous_intensity_duration_s": _minutes_to_seconds(
            data.get("vigorousIntensityMinutes")
        ),
        "resting_heart_rate_bpm": _number(data.get("restingHeartRate")),
        "minimum_heart_rate_bpm": _number(data.get("minHeartRate")),
        "maximum_heart_rate_bpm": _number(data.get("maxHeartRate")),
        "average_stress_native": _number(data.get("averageStressLevel")),
        "maximum_stress_native": _number(data.get("maxStressLevel")),
        "body_battery_charged_native": _number(data.get("bodyBatteryChargedValue")),
        "body_battery_drained_native": _number(data.get("bodyBatteryDrainedValue")),
        "body_battery_highest_native": _number(data.get("bodyBatteryHighestValue")),
        "body_battery_lowest_native": _number(data.get("bodyBatteryLowestValue")),
    }


def normalize_heart_rate(raw: Any, requested_date: str) -> NormalizedHeartRate:
    requested_date = validate_date(requested_date)
    data = _object_or_missing(raw, operation="heart-rate")
    if data is not None and not {
        "calendarDate",
        "heartRateValues",
        "restingHeartRate",
    }.intersection(data):
        raise MalformedRecoveryResponseError(
            "Garmin returned an unrecognized heart-rate response"
        )
    data = data or {}
    return {
        "date": requested_date,
        "resting_heart_rate_bpm": _number(data.get("restingHeartRate")),
        "minimum_heart_rate_bpm": _number(data.get("minHeartRate")),
        "maximum_heart_rate_bpm": _number(data.get("maxHeartRate")),
        "last_seven_days_average_resting_heart_rate_bpm": _number(
            data.get("lastSevenDaysAvgRestingHeartRate")
        ),
    }


def normalize_sleep(raw: Any, requested_date: str) -> NormalizedSleep:
    requested_date = validate_date(requested_date)
    data = _object_or_missing(raw, operation="sleep")
    if data is not None and "dailySleepDTO" not in data:
        raise MalformedRecoveryResponseError(
            "Garmin returned an unrecognized sleep response"
        )
    summary = data.get("dailySleepDTO") if data else None
    if summary is not None and not isinstance(summary, dict):
        raise MalformedRecoveryResponseError(
            "Garmin returned a malformed sleep summary"
        )
    summary = summary or {}
    scores = summary.get("sleepScores")
    if scores is not None and not isinstance(scores, dict):
        raise MalformedRecoveryResponseError(
            "Garmin returned a malformed sleep-score summary"
        )
    overall = scores.get("overall") if scores else None
    if overall is not None and not isinstance(overall, dict):
        raise MalformedRecoveryResponseError(
            "Garmin returned a malformed overall sleep score"
        )
    overall = overall or {}
    return {
        "date": requested_date,
        "sleep_start_time_utc": _timestamp_utc(summary.get("sleepStartTimestampGMT")),
        "sleep_end_time_utc": _timestamp_utc(summary.get("sleepEndTimestampGMT")),
        "total_sleep_duration_s": _number(summary.get("sleepTimeSeconds")),
        "deep_sleep_duration_s": _number(summary.get("deepSleepSeconds")),
        "light_sleep_duration_s": _number(summary.get("lightSleepSeconds")),
        "rem_sleep_duration_s": _number(summary.get("remSleepSeconds")),
        "awake_duration_s": _number(summary.get("awakeSleepSeconds")),
        "unmeasurable_duration_s": _number(summary.get("unmeasurableSleepSeconds")),
        "nap_duration_s": _number(summary.get("napTimeSeconds")),
        "sleep_score": _number(overall.get("value")),
        "sleep_score_status": _text(overall.get("qualifierKey")),
        "sleep_window_status": _text(summary.get("sleepWindowConfirmationType")),
    }


def _normalize_hrv_summary(raw: Any, requested_date: str) -> NormalizedHRV:
    if raw is None:
        summary: dict[str, Any] = {}
    elif not isinstance(raw, dict):
        raise MalformedRecoveryResponseError("Garmin returned a malformed HRV summary")
    else:
        summary = raw
    return {
        "date": requested_date,
        "weekly_average_ms": _number(summary.get("weeklyAvg")),
        "last_night_average_ms": _number(summary.get("lastNightAvg")),
        "last_night_five_minute_high_ms": _number(summary.get("lastNight5MinHigh")),
        "status": _text(summary.get("status")),
    }


def normalize_hrv(raw: Any, requested_date: str) -> NormalizedHRV:
    requested_date = validate_date(requested_date)
    data = _object_or_missing(raw, operation="HRV")
    if data is not None and "hrvSummary" not in data:
        raise MalformedRecoveryResponseError(
            "Garmin returned an unrecognized HRV response"
        )
    summary = data.get("hrvSummary") if data else None
    return _normalize_hrv_summary(summary, requested_date)


def normalize_hrv_range(raw: Any) -> list[NormalizedHRV]:
    data = _object_or_missing(raw, operation="HRV-range")
    if data is None:
        return []
    if "hrvSummaries" not in data:
        raise MalformedRecoveryResponseError(
            "Garmin returned an unrecognized HRV-range response"
        )
    summaries = data.get("hrvSummaries")
    if summaries is None:
        return []
    if not isinstance(summaries, list) or any(
        not isinstance(item, dict) for item in summaries
    ):
        raise MalformedRecoveryResponseError(
            "Garmin returned a malformed HRV-range response"
        )
    result: list[NormalizedHRV] = []
    for summary in summaries:
        calendar_date = summary.get("calendarDate")
        try:
            normalized_date = validate_date(calendar_date)
        except ValueError as exc:
            raise MalformedRecoveryResponseError(
                "Garmin returned an invalid date in the HRV-range response"
            ) from exc
        result.append(_normalize_hrv_summary(summary, normalized_date))
    return result


def normalize_body_battery(raw: Any, requested_date: str) -> NormalizedBodyBattery:
    requested_date = validate_date(requested_date)
    if raw is None or raw == []:
        entries: list[Any] = []
    elif not isinstance(raw, list):
        raise MalformedRecoveryResponseError(
            "Garmin returned a malformed Body Battery response"
        )
    else:
        entries = raw
    if any(not isinstance(item, dict) for item in entries):
        raise MalformedRecoveryResponseError(
            "Garmin returned a malformed Body Battery entry"
        )

    matching = next(
        (item for item in entries if item.get("date") == requested_date),
        entries[0] if len(entries) == 1 else None,
    )
    matching = matching or {}
    if matching and not {
        "date",
        "charged",
        "drained",
        "bodyBatteryValuesArray",
    }.intersection(matching):
        raise MalformedRecoveryResponseError(
            "Garmin returned an unrecognized Body Battery response"
        )

    samples = matching.get("bodyBatteryValuesArray")
    if samples is None:
        samples = []
    if not isinstance(samples, list):
        raise MalformedRecoveryResponseError(
            "Garmin returned malformed Body Battery samples"
        )
    values: list[float] = []
    for sample in samples:
        if not isinstance(sample, list | tuple) or len(sample) < 2:
            continue
        value = _number(sample[1])
        if value is not None:
            values.append(value)

    return {
        "date": requested_date,
        "charged_native": _number(matching.get("charged")),
        "drained_native": _number(matching.get("drained")),
        "highest_native": max(values, default=None),
        "lowest_native": min(values, default=None),
        "latest_native": values[-1] if values else None,
    }


def normalize_stress(raw: Any, requested_date: str) -> NormalizedStress:
    requested_date = validate_date(requested_date)
    data = _object_or_missing(raw, operation="stress")
    if data is not None and not {
        "calendarDate",
        "stressValuesArray",
        "avgStressLevel",
    }.intersection(data):
        raise MalformedRecoveryResponseError(
            "Garmin returned an unrecognized stress response"
        )
    data = data or {}
    return {
        "date": requested_date,
        "average_stress_native": _number(data.get("avgStressLevel")),
        "maximum_stress_native": _number(data.get("maxStressLevel")),
    }
