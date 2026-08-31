from __future__ import annotations

import inspect
from importlib.metadata import version
from typing import Any

import pytest
from garminconnect import (
    Garmin,
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
    WorkoutNotFoundError,
    WorkoutResponseError,
    WorkoutUncertainResultError,
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
        schedule_response: Any = None,
        scheduled_lookup_response: Any = None,
        error: Exception | None = None,
        upload_error: Exception | None = None,
        write_error: Exception | None = None,
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
        self.schedule_response = (
            {
                "workoutScheduleId": 8300000099,
                "calendarDate": "2030-06-15",
                "workout": saved(8100000099),
                "ownerId": 12345,
                "url": "https://private.invalid/schedule",
            }
            if schedule_response is None
            else schedule_response
        )
        self.scheduled_lookup_response = (
            scheduled(8300000099, 8100000099, "2030-06-15")
            if scheduled_lookup_response is None
            else scheduled_lookup_response
        )
        self.error = error
        self.upload_error = upload_error
        self.write_error = write_error
        self.calls: list[tuple[str, tuple[object, ...]]] = []

    def upload_workout(self, workout_json: object) -> Any:
        self.calls.append(("upload_workout", (workout_json,)))
        if self.upload_error is not None:
            raise self.upload_error
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

    def get_scheduled_workout_by_id(self, scheduled_workout_id: str) -> Any:
        self.calls.append(("get_scheduled_workout_by_id", (scheduled_workout_id,)))
        self._raise()
        return self.scheduled_lookup_response

    def schedule_workout(self, workout_id: str, date_str: str) -> Any:
        self.calls.append(("schedule_workout", (workout_id, date_str)))
        if self.write_error is not None:
            raise self.write_error
        return self.schedule_response

    def unschedule_workout(self, scheduled_workout_id: str) -> Any:
        self.calls.append(("unschedule_workout", (scheduled_workout_id,)))
        if self.write_error is not None:
            raise self.write_error
        return {}


def provider(client: SyntheticClient) -> GarminWorkoutProvider:
    return GarminWorkoutProvider(lambda: client)


def test_installed_write_wrappers_match_audited_single_call_source() -> None:
    assert version("garminconnect") == "0.3.11"

    schedule_source = inspect.getsource(Garmin.schedule_workout)
    unschedule_source = inspect.getsource(Garmin.unschedule_workout)
    upload_source = inspect.getsource(Garmin.upload_workout)

    assert upload_source.count("self.client.post(") == 1
    assert schedule_source.count("self.client.post(") == 1
    assert unschedule_source.count("self.client.delete(") == 1
    assert "connectapi(" not in upload_source
    assert "connectapi(" not in schedule_source
    assert "connectapi(" not in unschedule_source


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


def test_combined_workflow_uploads_once_then_schedules_only_returned_id() -> None:
    client = SyntheticClient()

    result = provider(client).create_and_schedule_running_workout(
        creation_definition(), "2030-06-15"
    )

    assert result == {
        "created": True,
        "workout_id": "8100000099",
        "scheduled": True,
        "already_scheduled": False,
        "scheduled_workout_id": "8300000099",
        "scheduled_date": "2030-06-15",
        "name": "Synthetic Creation Fixture",
        "sport_type": "running",
        "total_duration_s": 600.0,
        "total_distance_m": None,
        "partial_failure": False,
        "message": (
            "Exactly one new workout was created and scheduled in Garmin Connect."
        ),
    }
    assert client.calls == [
        ("upload_workout", (serialize_running_workout(creation_definition()),)),
        ("get_scheduled_workouts", (2030, 6)),
        ("schedule_workout", ("8100000099", "2030-06-15")),
    ]
    rendered = repr(result).casefold()
    assert "owner" not in rendered
    assert "url" not in rendered
    assert "private" not in rendered


def test_combined_workflow_validates_date_before_client_construction() -> None:
    constructions = 0

    def factory() -> SyntheticClient:
        nonlocal constructions
        constructions += 1
        return SyntheticClient()

    with pytest.raises(InvalidWorkoutRequestError):
        GarminWorkoutProvider(factory).create_and_schedule_running_workout(
            creation_definition(), "2030-6-15"
        )

    assert constructions == 0


@pytest.mark.parametrize("response", [{}, {"workoutId": True}, {"workoutId": "0"}])
def test_combined_malformed_upload_stops_before_schedule(response: object) -> None:
    client = SyntheticClient(upload_response=response)

    with pytest.raises(WorkoutResponseError):
        provider(client).create_and_schedule_running_workout(
            creation_definition(), "2030-06-15"
        )

    assert [call[0] for call in client.calls] == ["upload_workout"]


def test_combined_uncertain_upload_stops_without_retry_or_schedule() -> None:
    client = SyntheticClient(
        upload_error=GarminConnectConnectionError("private uncertain upload")
    )

    with pytest.raises(WorkoutUncertainResultError, match="uncertain") as raised:
        provider(client).create_and_schedule_running_workout(
            creation_definition(), "2030-06-15"
        )

    assert "private" not in str(raised.value)
    assert [call[0] for call in client.calls] == ["upload_workout"]


@pytest.mark.parametrize(
    ("upstream_error", "expected_error", "message"),
    [
        (
            GarminConnectAuthenticationError("private upload auth"),
            WorkoutAuthenticationError,
            "authentication failed",
        ),
        (
            GarminConnectTooManyRequestsError("private upload rate"),
            WorkoutEndpointError,
            "rate limit",
        ),
        (
            GarminConnectNotFoundError("private upload endpoint"),
            WorkoutEndpointError,
            "endpoint failed",
        ),
        (
            GarminConnectConnectionError("private upload uncertain"),
            WorkoutUncertainResultError,
            "uncertain",
        ),
    ],
)
def test_combined_upload_errors_are_secret_safe_and_never_retried(
    upstream_error: Exception,
    expected_error: type[Exception],
    message: str,
) -> None:
    client = SyntheticClient(upload_error=upstream_error)

    with pytest.raises(expected_error, match=message) as raised:
        provider(client).create_and_schedule_running_workout(
            creation_definition(), "2030-06-15"
        )

    assert "private" not in str(raised.value)
    assert [call[0] for call in client.calls] == ["upload_workout"]


def test_combined_unsupported_upload_stops_before_schedule() -> None:
    class UnsupportedClient:
        pass

    with pytest.raises(WorkoutUnsupportedError, match="does not support"):
        GarminWorkoutProvider(
            lambda: UnsupportedClient()  # type: ignore[arg-type]
        ).create_and_schedule_running_workout(creation_definition(), "2030-06-15")


def test_combined_schedule_failure_preserves_compact_partial_state() -> None:
    client = SyntheticClient(
        write_error=GarminConnectConnectionError("private uncertain schedule")
    )

    result = provider(client).create_and_schedule_running_workout(
        creation_definition(), "2030-06-15"
    )

    assert result["created"] is True
    assert result["workout_id"] == "8100000099"
    assert result["scheduled"] is False
    assert result["already_scheduled"] is False
    assert result["scheduled_workout_id"] is None
    assert result["partial_failure"] is True
    assert "scheduling is uncertain" in result["message"]
    assert "private" not in repr(result).casefold()
    assert [call[0] for call in client.calls] == [
        "upload_workout",
        "get_scheduled_workouts",
        "schedule_workout",
    ]


@pytest.mark.parametrize(
    ("schedule_error", "message"),
    [
        (
            GarminConnectAuthenticationError("private schedule auth"),
            "authentication expired",
        ),
        (
            GarminConnectTooManyRequestsError("private schedule rate"),
            "rate limit",
        ),
        (
            GarminConnectNotFoundError("private schedule endpoint"),
            "endpoint failed",
        ),
    ],
)
def test_combined_duplicate_read_failure_returns_secret_safe_partial_result(
    schedule_error: Exception, message: str
) -> None:
    class ReadFailureAfterUploadClient(SyntheticClient):
        def upload_workout(self, workout_json: object) -> Any:
            result = super().upload_workout(workout_json)
            self.error = schedule_error
            return result

    client = ReadFailureAfterUploadClient()

    result = provider(client).create_and_schedule_running_workout(
        creation_definition(), "2030-06-15"
    )

    assert result["created"] is True
    assert result["partial_failure"] is True
    assert message in result["message"]
    assert "private" not in repr(result).casefold()
    assert [call[0] for call in client.calls] == [
        "upload_workout",
        "get_scheduled_workouts",
    ]


def test_combined_malformed_schedule_response_is_uncertain_partial_state() -> None:
    client = SyntheticClient(schedule_response={})

    result = provider(client).create_and_schedule_running_workout(
        creation_definition(), "2030-06-15"
    )

    assert result["created"] is True
    assert result["scheduled"] is False
    assert result["scheduled_workout_id"] is None
    assert result["partial_failure"] is True
    assert "scheduling is uncertain" in result["message"]
    assert [call[0] for call in client.calls] == [
        "upload_workout",
        "get_scheduled_workouts",
        "schedule_workout",
    ]


def test_combined_exact_duplicate_skips_schedule_write() -> None:
    client = SyntheticClient(
        monthly_responses={
            (2030, 6): {
                "scheduledWorkouts": [scheduled(8300000099, 8100000099, "2030-06-15")]
            }
        }
    )

    result = provider(client).create_and_schedule_running_workout(
        creation_definition(), "2030-06-15"
    )

    assert result["created"] is True
    assert result["scheduled"] is False
    assert result["already_scheduled"] is True
    assert result["scheduled_workout_id"] == "8300000099"
    assert result["partial_failure"] is False
    assert [call[0] for call in client.calls] == [
        "upload_workout",
        "get_scheduled_workouts",
    ]


def test_combined_upload_blocks_dependency_auth_replay() -> None:
    class ReplayTransport:
        def __init__(self) -> None:
            self.http_attempts = 0
            self.refreshes = 0

        def _refresh_session(self) -> None:
            self.refreshes += 1

    class ReplayClient:
        def __init__(self) -> None:
            self.client = ReplayTransport()

        def upload_workout(self, workout_json: object) -> object:
            self.client.http_attempts += 1
            self.client._refresh_session()
            self.client.http_attempts += 1
            return {}

    client = ReplayClient()

    with pytest.raises(WorkoutAuthenticationError, match="authentication failed"):
        GarminWorkoutProvider(
            lambda: client  # type: ignore[arg-type]
        ).create_and_schedule_running_workout(creation_definition(), "2030-06-15")

    assert client.client.http_attempts == 1
    assert client.client.refreshes == 0
    client.client._refresh_session()
    assert client.client.refreshes == 1


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


def test_scheduled_range_includes_flat_future_calendar_workouts() -> None:
    def entry(schedule_id: int, day: str) -> dict[str, object]:
        return {
            "itemType": "workout",
            "id": schedule_id,
            "workoutId": 8100000021,
            "date": day,
            "title": "Synthetic planned run",
            "sportTypeKey": "running",
            "duration": 30,
            "distance": 5,
            "url": "https://private.invalid/ignored",
        }

    client = SyntheticClient(
        monthly_responses={
            (2030, 12): {"calendarItems": [entry(8300000011, "2030-12-31")]},
            (2031, 1): {
                "calendarItems": [
                    entry(8300000013, "2031-01-02"),
                    entry(8300000012, "2031-01-01"),
                    {**entry(8300000014, "2031-01-01"), "itemType": "activity"},
                ]
            },
        }
    )

    items = provider(client).scheduled_workouts("2030-12-31", "2031-01-01")

    assert items == [
        {
            "scheduled_workout_id": str(schedule_id),
            "scheduled_date": day,
            "workout_id": "8100000021",
            "name": "Synthetic planned run",
            "sport_type": "running",
            "description": None,
            "estimated_duration_s": None,
            "estimated_distance_m": None,
        }
        for schedule_id, day in (
            (8300000011, "2030-12-31"),
            (8300000012, "2031-01-01"),
        )
    ]
    assert client.calls == [
        ("get_scheduled_workouts", (2030, 12)),
        ("get_scheduled_workouts", (2031, 1)),
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


@pytest.mark.parametrize(
    ("workout_id", "scheduled_date"),
    [
        (8100000099, "2030-06-15"),
        ("0", "2030-06-15"),
        ("08100000099", "2030-06-15"),
        ("8100000099 ", "2030-06-15"),
        ("https://private.invalid/id", "2030-06-15"),
        ("8100000099", "2030-6-15"),
        ("8100000099", "2030-06-15T00:00:00Z"),
    ],
)
def test_schedule_rejects_invalid_request_before_client_construction(
    workout_id: object, scheduled_date: object
) -> None:
    constructions = 0

    def factory() -> SyntheticClient:
        nonlocal constructions
        constructions += 1
        return SyntheticClient()

    with pytest.raises(InvalidWorkoutRequestError):
        GarminWorkoutProvider(factory).schedule_existing_workout(
            workout_id,
            scheduled_date,  # type: ignore[arg-type]
        )

    assert constructions == 0


def test_schedule_checks_duplicate_then_writes_exactly_once() -> None:
    client = SyntheticClient()

    result = provider(client).schedule_existing_workout("8100000099", "2030-06-15")

    assert result == {
        "scheduled": True,
        "already_scheduled": False,
        "scheduled_workout_id": "8300000099",
        "workout_id": "8100000099",
        "scheduled_date": "2030-06-15",
        "message": "Exactly one existing workout was scheduled in Garmin Connect.",
    }
    assert client.calls == [
        ("get_scheduled_workouts", (2030, 6)),
        ("schedule_workout", ("8100000099", "2030-06-15")),
    ]
    rendered = repr(result).casefold()
    assert "owner" not in rendered
    assert "url" not in rendered
    assert "private" not in rendered


@pytest.mark.parametrize("flat_calendar", [False, True])
def test_exact_duplicate_is_idempotent_and_makes_no_schedule_call(
    flat_calendar: bool,
) -> None:
    response = {"scheduledWorkouts": [scheduled(8300000099, 8100000099, "2030-06-15")]}
    if flat_calendar:
        response = {
            "calendarItems": [
                {
                    "itemType": "workout",
                    "id": 8300000099,
                    "workoutId": 8100000099,
                    "date": "2030-06-15",
                }
            ]
        }
    client = SyntheticClient(monthly_responses={(2030, 6): response})

    result = provider(client).schedule_existing_workout("8100000099", "2030-06-15")

    assert result == {
        "scheduled": False,
        "already_scheduled": True,
        "scheduled_workout_id": "8300000099",
        "workout_id": "8100000099",
        "scheduled_date": "2030-06-15",
        "message": (
            "No calendar change: this workout is already scheduled on the "
            "requested date."
        ),
    }
    assert client.calls == [("get_scheduled_workouts", (2030, 6))]


@pytest.mark.parametrize(
    "response",
    [
        {},
        [],
        {"workoutId": 8100000099, "calendarDate": "2030-06-15"},
        {
            "workoutScheduleId": 8300000099,
            "workoutId": 8100000098,
            "calendarDate": "2030-06-15",
        },
        {
            "workoutScheduleId": 8300000099,
            "workoutId": 8100000099,
            "calendarDate": "2030-06-16",
        },
    ],
)
def test_schedule_rejects_malformed_or_mismatched_response_without_retry(
    response: object,
) -> None:
    client = SyntheticClient(schedule_response=response)

    with pytest.raises(WorkoutUncertainResultError, match="inspect Garmin Connect"):
        provider(client).schedule_existing_workout("8100000099", "2030-06-15")

    assert [call[0] for call in client.calls] == [
        "get_scheduled_workouts",
        "schedule_workout",
    ]


@pytest.mark.parametrize(
    ("upstream_error", "expected_error", "message"),
    [
        (
            GarminConnectAuthenticationError("private schedule auth text"),
            WorkoutAuthenticationError,
            "authentication failed",
        ),
        (
            GarminConnectTooManyRequestsError("private schedule rate text"),
            WorkoutEndpointError,
            "rate limit",
        ),
        (
            GarminConnectConnectionError("private uncertain text"),
            WorkoutUncertainResultError,
            "uncertain",
        ),
    ],
)
def test_schedule_maps_write_failures_safely_without_retry(
    upstream_error: Exception,
    expected_error: type[Exception],
    message: str,
) -> None:
    client = SyntheticClient(write_error=upstream_error)

    with pytest.raises(expected_error, match=message) as raised:
        provider(client).schedule_existing_workout("8100000099", "2030-06-15")

    assert "private" not in str(raised.value)
    assert [call[0] for call in client.calls] == [
        "get_scheduled_workouts",
        "schedule_workout",
    ]


def test_schedule_maps_unsupported_client_without_fallback() -> None:
    class UnsupportedClient:
        def get_scheduled_workouts(self, year: int, month: int) -> dict[str, object]:
            return {"calendarItems": []}

    with pytest.raises(WorkoutUnsupportedError, match="does not support"):
        GarminWorkoutProvider(
            lambda: UnsupportedClient()  # type: ignore[arg-type]
        ).schedule_existing_workout("8100000099", "2030-06-15")


def test_schedule_blocks_dependency_auth_replay_after_first_http_attempt() -> None:
    class ReplayTransport:
        def __init__(self) -> None:
            self.http_attempts = 0
            self.refreshes = 0

        def _refresh_session(self) -> None:
            self.refreshes += 1

    class ReplayClient:
        def __init__(self) -> None:
            self.client = ReplayTransport()

        def get_scheduled_workouts(self, year: int, month: int) -> dict[str, object]:
            return {"calendarItems": []}

        def schedule_workout(self, workout_id: str, date_str: str) -> object:
            self.client.http_attempts += 1
            self.client._refresh_session()
            self.client.http_attempts += 1
            return {}

    client = ReplayClient()

    with pytest.raises(WorkoutAuthenticationError, match="authentication failed"):
        GarminWorkoutProvider(
            lambda: client  # type: ignore[arg-type]
        ).schedule_existing_workout("8100000099", "2030-06-15")

    assert client.client.http_attempts == 1
    assert client.client.refreshes == 0
    client.client._refresh_session()
    assert client.client.refreshes == 1


def test_scheduled_workout_lookup_returns_only_normalized_assignment() -> None:
    client = SyntheticClient(
        scheduled_lookup_response={
            **scheduled(8300000099, 8100000099, "2030-06-15"),
            "ownerId": 12345,
            "url": "https://private.invalid/schedule",
        }
    )

    result = provider(client).scheduled_workout("8300000099")

    assert result["scheduled_workout_id"] == "8300000099"
    assert result["workout_id"] == "8100000099"
    assert result["scheduled_date"] == "2030-06-15"
    assert "owner" not in repr(result).casefold()
    assert "url" not in repr(result).casefold()
    assert client.calls == [("get_scheduled_workout_by_id", ("8300000099",))]


def test_scheduled_workout_lookup_maps_not_found_safely() -> None:
    client = SyntheticClient(
        error=GarminConnectNotFoundError("private missing assignment")
    )

    with pytest.raises(WorkoutNotFoundError, match="not found") as raised:
        provider(client).scheduled_workout("8300000099")

    assert "private" not in str(raised.value)


def test_unschedule_reads_assignment_then_deletes_assignment_once() -> None:
    client = SyntheticClient()

    result = provider(client).unschedule_existing_workout("8300000099")

    assert result == {
        "unscheduled": True,
        "scheduled_workout_id": "8300000099",
        "workout_id": "8100000099",
        "scheduled_date": "2030-06-15",
        "workout_deleted": False,
        "message": (
            "Only the Garmin calendar assignment was removed; the workout "
            "template was not deleted."
        ),
    }
    assert client.calls == [
        ("get_scheduled_workout_by_id", ("8300000099",)),
        ("unschedule_workout", ("8300000099",)),
    ]


def test_unschedule_uncertain_failure_is_not_retried_or_rolled_back() -> None:
    client = SyntheticClient(
        write_error=GarminConnectConnectionError("private uncertain delete text")
    )

    with pytest.raises(WorkoutUncertainResultError, match="uncertain") as raised:
        provider(client).unschedule_existing_workout("8300000099")

    assert "private" not in str(raised.value)
    assert [call[0] for call in client.calls] == [
        "get_scheduled_workout_by_id",
        "unschedule_workout",
    ]
