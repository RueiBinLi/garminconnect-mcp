from __future__ import annotations

import math
from datetime import date
from typing import Any, TypedDict


class NormalizedWorkout(TypedDict):
    """Compact saved-workout metadata with explicit measurement units."""

    workout_id: str | None
    name: str | None
    sport_type: str | None
    description: str | None
    estimated_duration_s: float | None
    estimated_distance_m: float | None


class NormalizedScheduledWorkout(NormalizedWorkout):
    """Compact scheduled-workout metadata keyed by a Garmin calendar date."""

    scheduled_workout_id: str | None
    scheduled_date: str | None


class MalformedWorkoutResponseError(RuntimeError):
    """Raised when Garmin returns an unexpected workout response shape."""


_KNOWN_WORKOUT_KEYS = {
    "description",
    "estimatedDistanceInMeters",
    "estimatedDurationInSecs",
    "sportType",
    "workoutId",
    "workoutName",
}
_SCHEDULE_ID_KEYS = (
    "scheduledWorkoutId",
    "workoutScheduleId",
    "calendarScheduleId",
    "scheduleId",
)
_SCHEDULE_DATE_KEYS = (
    "calendarDate",
    "scheduleDate",
    "workoutScheduleDate",
    "date",
)


def _first_present(data: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        value = data.get(key)
        if value is not None:
            return value
    return None


def _identifier(value: Any) -> str | None:
    if isinstance(value, bool) or not isinstance(value, int | str):
        return None
    normalized = str(value).strip()
    return normalized or None


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    normalized = float(value)
    return normalized if math.isfinite(normalized) and normalized >= 0 else None


def _text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


def _sport_type(value: Any) -> str | None:
    if isinstance(value, dict):
        value = _first_present(value, ("sportTypeKey", "typeKey", "key"))
    return _text(value)


def normalize_workout(raw: Any) -> NormalizedWorkout:
    """Normalize one saved workout without retaining Garmin's raw response."""
    if (
        not isinstance(raw, dict)
        or not raw
        or not _KNOWN_WORKOUT_KEYS.intersection(raw)
    ):
        raise MalformedWorkoutResponseError(
            "Garmin returned an unrecognized workout response"
        )

    return {
        "workout_id": _identifier(_first_present(raw, ("workoutId", "id"))),
        "name": _text(_first_present(raw, ("workoutName", "name"))),
        "sport_type": _sport_type(
            _first_present(raw, ("sportType", "activityType", "sport"))
        ),
        "description": _text(raw.get("description")),
        "estimated_duration_s": _number(
            _first_present(
                raw,
                (
                    "estimatedDurationInSecs",
                    "estimatedDurationSecs",
                    "estimatedDurationSeconds",
                ),
            )
        ),
        "estimated_distance_m": _number(
            _first_present(
                raw,
                (
                    "estimatedDistanceInMeters",
                    "estimatedDistanceMeters",
                    "estimatedDistance",
                ),
            )
        ),
    }


def normalize_scheduled_workout(raw: Any) -> NormalizedScheduledWorkout:
    """Normalize one Garmin calendar workout without inferring an instant."""
    if not isinstance(raw, dict) or not raw:
        raise MalformedWorkoutResponseError(
            "Garmin returned an unrecognized scheduled-workout response"
        )

    template = raw.get("workout")
    if not isinstance(template, dict):
        if raw.get("itemType") == "workout":
            # Monthly calendar entries are flat. Their `id` identifies the
            # assignment, never the template. Generic duration/distance fields
            # have no verified units here and must not become estimates.
            template = {
                "workoutId": raw.get("workoutId"),
                "workoutName": raw.get("title"),
                "sportType": raw.get("sportTypeKey"),
            }
        else:
            template = raw
    workout = normalize_workout(template)

    schedule_id = _first_present(raw, _SCHEDULE_ID_KEYS)
    if schedule_id is None and raw.get("itemType") == "workout":
        schedule_id = raw.get("id")

    scheduled_date = _text(_first_present(raw, _SCHEDULE_DATE_KEYS))
    if scheduled_date is not None:
        try:
            if date.fromisoformat(scheduled_date).isoformat() != scheduled_date:
                raise ValueError
        except ValueError as exc:
            raise MalformedWorkoutResponseError(
                "Garmin returned a malformed scheduled-workout date"
            ) from exc

    return {
        "scheduled_workout_id": _identifier(schedule_id),
        "scheduled_date": scheduled_date,
        **workout,
    }


def workout_items(raw: Any) -> list[dict[str, Any]]:
    """Extract saved workouts from only supported response envelopes."""
    items: Any = raw
    if isinstance(raw, dict):
        items = raw.get("workouts")
    if not isinstance(items, list) or any(not isinstance(item, dict) for item in items):
        raise MalformedWorkoutResponseError(
            "Garmin returned a malformed saved-workouts response"
        )
    return items


def scheduled_workout_items(raw: Any) -> list[dict[str, Any]]:
    """Extract only workout entries from Garmin's supported calendar envelopes."""
    items: Any = raw
    calendar_envelope = False
    if isinstance(raw, dict):
        if "scheduledWorkouts" in raw:
            items = raw["scheduledWorkouts"]
        elif "workouts" in raw:
            items = raw["workouts"]
        elif "calendarItems" in raw:
            items = raw["calendarItems"]
            calendar_envelope = True
        else:
            items = None

    if not isinstance(items, list) or any(not isinstance(item, dict) for item in items):
        raise MalformedWorkoutResponseError(
            "Garmin returned a malformed scheduled-workouts response"
        )
    if not calendar_envelope:
        return items

    return [
        item
        for item in items
        if item.get("itemType") == "workout"
        or (
            item.get("itemType") is None
            and isinstance(item.get("workout"), dict)
            and _first_present(item, _SCHEDULE_ID_KEYS) is not None
        )
    ]


def workout_is_running(workout: NormalizedWorkout) -> bool:
    sport_type = workout["sport_type"]
    return sport_type is not None and sport_type.casefold() in {
        "running",
        "trail_running",
    }
