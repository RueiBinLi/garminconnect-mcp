from __future__ import annotations

from typing import Any

import pytest
from garminconnect import (
    GarminConnectAuthenticationError,
    GarminConnectConnectionError,
    GarminConnectNotFoundError,
    GarminConnectTooManyRequestsError,
)

from garminconnect_mcp.provider import (
    GarminWorkoutProvider,
    InvalidWorkoutRequestError,
    WorkoutAuthenticationError,
    WorkoutEndpointError,
    WorkoutResponseError,
    WorkoutUnsupportedError,
)
from garminconnect_mcp.workout_builder import (
    WorkoutDefinition,
    serialize_running_workout,
)


def saved(workout_id: int, sport: str = "running") -> dict[str, object]:
    return {
        "workoutId": workout_id,
        "workoutName": f"Synthetic {sport}",
        "sportType": {"sportTypeKey": sport},
    }


def scheduled(schedule_id: int, workout_id: int, day: str) -> dict[str, object]:
    return {
        "workoutScheduleId": schedule_id,
        "calendarDate": day,
        "workout": saved(workout_id),
    }


class SyntheticClient:
    def __init__(
        self,
        *,
        saved_response: Any = None,
        my_workouts_response: Any = None,
        monthly_responses: dict[tuple[int, int], Any] | None = None,
        upload_response: Any = None,
        error: Exception | None = None,
    ) -> None:
        self.saved_response = [] if saved_response is None else saved_response
        self.my_workouts_response = (
            self.saved_response
            if my_workouts_response is None
            else my_workouts_response
        )
        self.monthly_responses = monthly_responses or {}
        self.upload_response = (
            {
                "workoutId": 8100000099,
                "workoutName": "private response name",
                "sportType": {"sportTypeKey": "running"},
                "ownerId": 12345,
                "url": "https://private.invalid/workout",
            }
            if upload_response is None
            else upload_response
        )
        self.error = error
        self.calls: list[tuple[str, tuple[object, ...]]] = []

    def upload_workout(self, workout_json: object) -> Any:
        self.calls.append(("upload_workout", (workout_json,)))
        self._raise()
        return self.upload_response

    def _raise(self) -> None:
        if self.error is not None:
            raise self.error

    def get_workouts(self, start: int = 0, limit: int = 100) -> Any:
        self.calls.append(("get_workouts", (start, limit)))
        self._raise()
        return self.saved_response

    def connectapi(self, path: str, **kwargs: Any) -> Any:
        self.calls.append(("connectapi", (path, kwargs)))
        self._raise()
        return self.my_workouts_response

    def get_scheduled_workouts(self, year: int, month: int) -> Any:
        self.calls.append(("get_scheduled_workouts", (year, month)))
        self._raise()
        return self.monthly_responses.get((year, month), {"calendarItems": []})


def provider(client: SyntheticClient) -> GarminWorkoutProvider:
    return GarminWorkoutProvider(lambda: client)


def creation_definition() -> WorkoutDefinition:
    return WorkoutDefinition.model_validate(
        {
            "name": "Synthetic Creation Fixture",
            "steps": [
                {
                    "step_type": "run",
                    "duration": {"duration_type": "time", "duration_s": 600},
                }
            ],
        },
        strict=True,
    )


def test_create_running_workout_uploads_exact_serializer_output_once() -> None:
    client = SyntheticClient()
    definition = creation_definition()

    result = provider(client).create_running_workout(definition)

    assert result == {
        "created": True,
        "workout_id": "8100000099",
        "name": "Synthetic Creation Fixture",
        "sport_type": "running",
        "total_duration_s": 600.0,
        "total_distance_m": None,
        "scheduled": False,
        "message": "Workout created in Garmin Connect but not scheduled.",
    }
    assert client.calls == [
        ("upload_workout", (serialize_running_workout(definition),))
    ]
    rendered = repr(result).casefold()
    assert "private response name" not in rendered
    assert "owner" not in rendered
    assert "url" not in rendered


@pytest.mark.parametrize(
    "response",
    [
        {},
        [],
        {"workoutName": "Synthetic response without ID"},
        {"workoutId": True, "workoutName": "Synthetic invalid ID"},
    ],
)
def test_create_running_workout_rejects_malformed_responses_without_retry(
    response: object,
) -> None:
    client = SyntheticClient(upload_response=response)

    with pytest.raises(WorkoutResponseError, match="response|workout ID"):
        provider(client).create_running_workout(creation_definition())

    assert [call[0] for call in client.calls] == ["upload_workout"]


@pytest.mark.parametrize(
    ("upstream_error", "expected_error", "message"),
    [
        (
            GarminConnectAuthenticationError("private creation auth text"),
            WorkoutAuthenticationError,
            "authentication failed",
        ),
        (
            GarminConnectTooManyRequestsError("private creation rate text"),
            WorkoutEndpointError,
            "rate limit",
        ),
        (
            GarminConnectConnectionError("private creation endpoint text"),
            WorkoutEndpointError,
            "endpoint failed",
        ),
    ],
)
def test_create_running_workout_maps_failures_without_retry_or_private_text(
    upstream_error: Exception,
    expected_error: type[Exception],
    message: str,
) -> None:
    client = SyntheticClient(error=upstream_error)

    with pytest.raises(expected_error, match=message) as raised:
        provider(client).create_running_workout(creation_definition())

    assert "private creation" not in str(raised.value)
    assert [call[0] for call in client.calls] == ["upload_workout"]


def test_create_running_workout_maps_missing_upload_support_safely() -> None:
    class UnsupportedClient:
        pass

    with pytest.raises(WorkoutUnsupportedError, match="does not support"):
        GarminWorkoutProvider(lambda: UnsupportedClient()).create_running_workout(
            creation_definition()
        )


def test_saved_workouts_has_bounded_pagination_and_ui_order() -> None:
    client = SyntheticClient(saved_response=[saved(8100000012), saved(8100000011)])

    source_count, items = provider(client).saved_workouts(
        start=5, limit=20, running_only=False
    )

    assert source_count == 2
    assert [item["workout_id"] for item in items] == ["8100000012", "8100000011"]
    assert client.calls == [
        (
            "connectapi",
            (
                "/workout-service/workouts",
                {
                    "params": {
                        "start": 6,
                        "limit": 20,
                        "myWorkoutsOnly": "true",
                        "sharedWorkoutsOnly": "false",
                        "includeAtp": "false",
                        "orderBy": "UPDATE_DATE",
                        "orderSeq": "DESC",
                    }
                },
            ),
        )
    ]


def test_saved_workouts_matches_garmin_my_workouts_filter() -> None:
    client = SyntheticClient(
        saved_response=[saved(8100000013)],
        my_workouts_response=[],
    )

    assert provider(client).saved_workouts(start=0, limit=20, running_only=False) == (
        0,
        [],
    )
    assert client.calls == [
        (
            "connectapi",
            (
                "/workout-service/workouts",
                {
                    "params": {
                        "start": 1,
                        "limit": 20,
                        "myWorkoutsOnly": "true",
                        "sharedWorkoutsOnly": "false",
                        "includeAtp": "false",
                        "orderBy": "UPDATE_DATE",
                        "orderSeq": "DESC",
                    }
                },
            ),
        )
    ]


@pytest.mark.parametrize(
    ("start", "limit", "running_only"),
    [(-1, 20, False), (0, 0, False), (0, 101, False), (0, 20, "yes")],
)
def test_saved_workouts_rejects_invalid_pagination_before_call(
    start: int, limit: int, running_only: bool
) -> None:
    client = SyntheticClient()

    with pytest.raises(InvalidWorkoutRequestError):
        provider(client).saved_workouts(
            start=start, limit=limit, running_only=running_only
        )

    assert client.calls == []


def test_saved_workouts_filters_running_within_fetched_page() -> None:
    client = SyntheticClient(
        saved_response=[saved(8100000013, "cycling"), saved(8100000014)]
    )

    source_count, items = provider(client).saved_workouts(
        start=0, limit=2, running_only=True
    )

    assert source_count == 2
    assert [item["workout_id"] for item in items] == ["8100000014"]
    assert client.calls[0][1][1]["params"]["sportTypeKey"] == "running"


def test_scheduled_range_fetches_intersecting_months_and_filters_dates() -> None:
    client = SyntheticClient(
        monthly_responses={
            (2030, 4): {
                "calendarItems": [
                    scheduled(8300000011, 8100000021, "2030-04-29"),
                    scheduled(8300000012, 8100000022, "2030-04-30"),
                    {"calendarDate": "2030-04-30", "activity": {"ignored": True}},
                ]
            },
            (2030, 5): {
                "calendarItems": [
                    scheduled(8300000014, 8100000024, "2030-05-02"),
                    scheduled(8300000013, 8100000023, "2030-05-01"),
                    scheduled(8300000015, 8100000025, "2030-05-03"),
                ]
            },
        }
    )

    items = provider(client).scheduled_workouts("2030-04-30", "2030-05-02")

    assert [item["scheduled_workout_id"] for item in items] == [
        "8300000012",
        "8300000013",
        "8300000014",
    ]
    assert client.calls == [
        ("get_scheduled_workouts", (2030, 4)),
        ("get_scheduled_workouts", (2030, 5)),
    ]


@pytest.mark.parametrize(
    ("start_date", "end_date"),
    [
        ("2030-4-01", "2030-04-02"),
        ("2030-02-30", "2030-04-02"),
        ("2030-04-02", "2030-04-01"),
        ("2030-04-01", "2030-05-02"),
    ],
)
def test_scheduled_workouts_rejects_invalid_ranges_before_call(
    start_date: str, end_date: str
) -> None:
    client = SyntheticClient()

    with pytest.raises(InvalidWorkoutRequestError):
        provider(client).scheduled_workouts(start_date, end_date)

    assert client.calls == []


def test_provider_returns_empty_results_gracefully() -> None:
    client = SyntheticClient()

    assert provider(client).saved_workouts(start=0, limit=20, running_only=False) == (
        0,
        [],
    )
    assert provider(client).scheduled_workouts("2030-04-01", "2030-04-07") == []


@pytest.mark.parametrize(
    ("upstream_error", "expected_error", "message"),
    [
        (
            GarminConnectAuthenticationError("private upstream text"),
            WorkoutAuthenticationError,
            "authentication failed",
        ),
        (
            GarminConnectConnectionError("private upstream text"),
            WorkoutEndpointError,
            "endpoint failed",
        ),
        (
            GarminConnectNotFoundError("private upstream text"),
            WorkoutEndpointError,
            "endpoint failed",
        ),
        (
            GarminConnectTooManyRequestsError("private upstream text"),
            WorkoutEndpointError,
            "rate limit",
        ),
    ],
)
def test_provider_maps_upstream_failures_to_safe_errors(
    upstream_error: Exception,
    expected_error: type[Exception],
    message: str,
) -> None:
    with pytest.raises(expected_error, match=message) as raised:
        provider(SyntheticClient(error=upstream_error)).saved_workouts(
            start=0, limit=20, running_only=False
        )

    assert "private upstream text" not in str(raised.value)


def test_provider_maps_malformed_envelope_to_stable_error() -> None:
    with pytest.raises(WorkoutResponseError, match="malformed"):
        provider(SyntheticClient(saved_response={"workouts": {}})).saved_workouts(
            start=0, limit=20, running_only=False
        )
