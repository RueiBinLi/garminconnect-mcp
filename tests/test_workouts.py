from __future__ import annotations

import pytest

from garminconnect_mcp.workouts import (
    MalformedWorkoutResponseError,
    normalize_scheduled_workout,
    normalize_workout,
    scheduled_workout_items,
    workout_is_running,
    workout_items,
)


def synthetic_workout(workout_id: int = 8100000001) -> dict[str, object]:
    return {
        "workoutId": workout_id,
        "workoutName": "Synthetic Running Template",
        "description": "Synthetic fixture only",
        "sportType": {"sportTypeId": 1, "sportTypeKey": "running"},
        "estimatedDurationInSecs": 1800,
        "estimatedDistanceInMeters": 5000,
        "ownerId": 8200000001,
        "workoutSegments": [{"largeNestedPayload": [1, 2, 3]}],
    }


def test_normalize_workout_preserves_only_compact_fields() -> None:
    assert normalize_workout(synthetic_workout()) == {
        "workout_id": "8100000001",
        "name": "Synthetic Running Template",
        "sport_type": "running",
        "description": "Synthetic fixture only",
        "estimated_duration_s": 1800.0,
        "estimated_distance_m": 5000.0,
    }


def test_normalize_workout_represents_unavailable_fields_as_none() -> None:
    result = normalize_workout({"workoutId": 8100000002})

    assert result["workout_id"] == "8100000002"
    assert all(value is None for key, value in result.items() if key != "workout_id")


def test_normalize_workout_rejects_invalid_measurements() -> None:
    result = normalize_workout(
        {
            "workoutId": 8100000003,
            "estimatedDurationInSecs": "1800",
            "estimatedDistanceInMeters": -1,
        }
    )

    assert result["estimated_duration_s"] is None
    assert result["estimated_distance_m"] is None


@pytest.mark.parametrize("raw", [None, [], {}, {"unexpected": "shape"}])
def test_normalize_workout_rejects_malformed_response(raw: object) -> None:
    with pytest.raises(MalformedWorkoutResponseError, match="workout response"):
        normalize_workout(raw)


def test_normalize_scheduled_workout_uses_calendar_date_without_timezone() -> None:
    result = normalize_scheduled_workout(
        {
            "workoutScheduleId": 8300000001,
            "calendarDate": "2030-04-12",
            "workout": synthetic_workout(),
            "createdDate": "2030-04-01",
        }
    )

    assert result == {
        "scheduled_workout_id": "8300000001",
        "scheduled_date": "2030-04-12",
        "workout_id": "8100000001",
        "name": "Synthetic Running Template",
        "sport_type": "running",
        "description": "Synthetic fixture only",
        "estimated_duration_s": 1800.0,
        "estimated_distance_m": 5000.0,
    }


def test_normalize_scheduled_workout_keeps_missing_schedule_fields_null() -> None:
    result = normalize_scheduled_workout({"workout": synthetic_workout()})

    assert result["scheduled_workout_id"] is None
    assert result["scheduled_date"] is None


def test_normalize_scheduled_workout_rejects_timestamp_as_calendar_date() -> None:
    with pytest.raises(MalformedWorkoutResponseError, match="date"):
        normalize_scheduled_workout(
            {
                "workoutScheduleId": 8300000002,
                "calendarDate": "2030-04-12T06:00:00Z",
                "workout": synthetic_workout(),
            }
        )


def test_workout_items_accepts_list_and_known_envelope() -> None:
    items = [synthetic_workout()]

    assert workout_items(items) is items
    assert workout_items({"workouts": items}) is items


def test_scheduled_items_discard_non_workout_calendar_items() -> None:
    scheduled = {
        "workoutScheduleId": 8300000003,
        "calendarDate": "2030-04-13",
        "workout": synthetic_workout(),
    }
    other_calendar_item = {
        "calendarDate": "2030-04-13",
        "activity": {"ignored": True},
    }

    assert scheduled_workout_items(
        {"calendarItems": [other_calendar_item, scheduled]}
    ) == [scheduled]


@pytest.mark.parametrize(
    "raw",
    [None, {}, {"workouts": {}}, {"calendarItems": ["bad item"]}],
)
def test_item_extractors_reject_malformed_envelopes(raw: object) -> None:
    with pytest.raises(MalformedWorkoutResponseError):
        workout_items(raw)
    with pytest.raises(MalformedWorkoutResponseError):
        scheduled_workout_items(raw)


def test_running_filter_requires_known_running_sport() -> None:
    assert workout_is_running(normalize_workout(synthetic_workout())) is True
    assert (
        workout_is_running(
            normalize_workout(
                {
                    "workoutId": 8100000004,
                    "sportType": {"sportTypeKey": "cycling"},
                }
            )
        )
        is False
    )
