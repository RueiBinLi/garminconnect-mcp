from __future__ import annotations

from collections.abc import Callable
from datetime import date
from threading import RLock
from typing import Any, Protocol

from garminconnect import (
    GarminConnectAuthenticationError,
    GarminConnectConnectionError,
    GarminConnectNotFoundError,
    GarminConnectTooManyRequestsError,
)

from .activities import (
    NormalizedActivity,
    NormalizedActivitySplits,
    activity_is_running,
    activity_items,
    normalize_activity,
    normalize_activity_splits,
    normalized_activity_date,
)
from .aerobic_drift import AerobicDriftSummary, analyze_aerobic_drift
from .heart_rate_zones import (
    MalformedHeartRateZoneResponseError,
    NormalizedHeartRateZones,
    normalize_running_heart_rate_zones,
)
from .recovery import (
    NormalizedBodyBattery,
    NormalizedDailyStatistics,
    NormalizedHeartRate,
    NormalizedHRV,
    NormalizedSleep,
    NormalizedStress,
    normalize_body_battery,
    normalize_daily_statistics,
    normalize_heart_rate,
    normalize_hrv,
    normalize_hrv_range,
    normalize_sleep,
    normalize_stress,
    validate_date,
)
from .workout_builder import (
    WorkoutDefinition,
    aggregate_workout,
    serialize_running_workout,
)
from .workouts import (
    MalformedWorkoutResponseError,
    NormalizedScheduledWorkout,
    NormalizedWorkout,
    normalize_scheduled_workout,
    normalize_workout,
    scheduled_workout_items,
    workout_is_running,
    workout_items,
)

MAX_ACTIVITY_PAGE_SIZE = 100
MAX_RUNNING_DATE_RANGE_DAYS = 42
MAX_HRV_RANGE_DAYS = 14
MAX_WORKOUT_PAGE_SIZE = 100
MAX_SCHEDULED_WORKOUT_RANGE_DAYS = 31


class GarminClient(Protocol):
    def connectapi(self, path: str, **kwargs: Any) -> Any: ...

    def get_activities(
        self, start: int = 0, limit: int = 20, activitytype: str | None = None
    ) -> Any: ...

    def get_activity(self, activity_id: str) -> Any: ...

    def get_activity_splits(self, activity_id: str) -> Any: ...

    def get_activity_typed_splits(self, activity_id: str) -> Any: ...

    def get_activity_details(
        self, activity_id: str, maxchart: int = 2000, maxpoly: int = 4000
    ) -> Any: ...

    def get_activities_by_date(
        self,
        startdate: str,
        enddate: str | None = None,
        activitytype: str | None = None,
        sortorder: str | None = None,
    ) -> Any: ...

    def get_stats(self, cdate: str) -> Any: ...

    def get_heart_rates(self, cdate: str) -> Any: ...

    def get_sleep_data(self, cdate: str) -> Any: ...

    def get_hrv_data(self, cdate: str) -> Any: ...

    def get_hrv_data_range(self, start: str, end: str) -> Any: ...

    def get_body_battery(self, startdate: str, enddate: str | None = None) -> Any: ...

    def get_stress_data(self, cdate: str) -> Any: ...

    def get_heart_rate_zones(self) -> Any: ...

    def get_scheduled_workouts(self, year: int, month: int) -> Any: ...

    def get_scheduled_workout_by_id(self, scheduled_workout_id: str) -> Any: ...

    def upload_workout(self, workout_json: dict[str, Any]) -> Any: ...

    def schedule_workout(self, workout_id: str, date_str: str) -> Any: ...

    def unschedule_workout(self, scheduled_workout_id: str) -> Any: ...


class ActivityProviderError(RuntimeError):
    """Base class for stable, secret-safe activity provider failures."""


class ActivityAuthenticationError(ActivityProviderError):
    pass


class ActivityEndpointError(ActivityProviderError):
    pass


class ActivityNotFoundError(ActivityProviderError):
    pass


class InvalidActivityRequestError(ActivityProviderError):
    pass


class GarminActivityProvider:
    """Isolate unofficial Garmin activity calls from MCP/application code."""

    def __init__(self, client_factory: Callable[[], GarminClient]) -> None:
        self._client_factory = client_factory

    def recent_activities(
        self, *, start: int, limit: int, running_only: bool
    ) -> list[NormalizedActivity]:
        if not isinstance(running_only, bool):
            raise InvalidActivityRequestError("running_only must be a boolean")
        if isinstance(start, bool) or not isinstance(start, int) or start < 0:
            raise InvalidActivityRequestError("start must be a non-negative integer")
        if (
            isinstance(limit, bool)
            or not isinstance(limit, int)
            or not 1 <= limit <= MAX_ACTIVITY_PAGE_SIZE
        ):
            raise InvalidActivityRequestError(
                f"limit must be between 1 and {MAX_ACTIVITY_PAGE_SIZE}"
            )

        raw = self._call(
            "recent activities",
            lambda client: client.get_activities(
                start, limit, activitytype="running" if running_only else None
            ),
        )
        normalized = [normalize_activity(item) for item in activity_items(raw)]
        if running_only:
            return [item for item in normalized if activity_is_running(item)]
        return normalized

    def activity(self, activity_id: str) -> NormalizedActivity:
        normalized_id = self._activity_id(activity_id)

        raw = self._call(
            "activity details",
            lambda client: client.get_activity(normalized_id),
            not_found=True,
        )
        return normalize_activity(raw)

    def activity_splits(
        self, activity_id: str, *, mode: str = "laps"
    ) -> NormalizedActivitySplits:
        normalized_id = self._activity_id(activity_id)
        if mode != "laps":
            raise InvalidActivityRequestError("mode must be 'laps'")
        raw = self._call(
            "activity splits",
            lambda client: client.get_activity_splits(normalized_id),
            not_found=True,
        )
        return normalize_activity_splits(raw, activity_id=normalized_id)

    def aerobic_drift(self, activity_id: str) -> AerobicDriftSummary:
        normalized_id = self._activity_id(activity_id)
        details = self._call(
            "activity details",
            lambda client: client.get_activity_details(
                normalized_id, maxchart=1000, maxpoly=0
            ),
            not_found=True,
        )
        recorded_laps = self._call(
            "activity splits",
            lambda client: client.get_activity_splits(normalized_id),
            not_found=True,
        )
        typed_splits = self._call(
            "typed activity splits",
            lambda client: client.get_activity_typed_splits(normalized_id),
            not_found=True,
        )
        return analyze_aerobic_drift(
            normalized_id,
            details,
            recorded_laps=recorded_laps,
            typed_splits=typed_splits,
        )

    def running_activities_by_date(
        self, start_date: str, end_date: str
    ) -> list[NormalizedActivity]:
        """Return compact running activities for an inclusive bounded range."""
        start_date = self._date(start_date, name="start_date")
        end_date = self._date(end_date, name="end_date")
        start = date.fromisoformat(start_date)
        end = date.fromisoformat(end_date)
        if start > end:
            raise InvalidActivityRequestError(
                "start_date must be on or before end_date"
            )
        day_count = (end - start).days + 1
        if day_count > MAX_RUNNING_DATE_RANGE_DAYS:
            raise InvalidActivityRequestError(
                "running activity ranges must contain at most "
                f"{MAX_RUNNING_DATE_RANGE_DAYS} days"
            )

        raw = self._call(
            "running activities by date",
            lambda client: client.get_activities_by_date(
                start_date,
                end_date,
                activitytype="running",
                sortorder="asc",
            ),
        )
        normalized = [normalize_activity(item) for item in activity_items(raw)]
        result: list[NormalizedActivity] = []
        for item in normalized:
            activity_day = normalized_activity_date(item)
            if activity_is_running(item) and (
                activity_day is None or start <= activity_day <= end
            ):
                result.append(item)
        return result

    @staticmethod
    def _date(value: Any, *, name: str) -> str:
        try:
            return validate_date(value, name=name)
        except ValueError as exc:
            raise InvalidActivityRequestError(str(exc)) from exc

    @staticmethod
    def _activity_id(activity_id: Any) -> str:
        normalized_id = activity_id.strip() if isinstance(activity_id, str) else ""
        if not normalized_id.isdecimal() or int(normalized_id) <= 0:
            raise InvalidActivityRequestError(
                "activity_id must be a positive numeric identifier"
            )
        return normalized_id

    def _call(
        self,
        operation: str,
        callback: Callable[[GarminClient], Any],
        *,
        not_found: bool = False,
    ) -> Any:
        try:
            return callback(self._client_factory())
        except GarminConnectNotFoundError as exc:
            if not_found:
                raise ActivityNotFoundError("Garmin activity was not found") from exc
            raise ActivityEndpointError(
                f"Garmin {operation} endpoint was unavailable"
            ) from exc
        except GarminConnectAuthenticationError as exc:
            raise ActivityAuthenticationError(
                "Garmin authentication failed; refresh the saved login"
            ) from exc
        except GarminConnectTooManyRequestsError as exc:
            raise ActivityEndpointError(
                f"Garmin {operation} endpoint rate limit was reached"
            ) from exc
        except GarminConnectConnectionError as exc:
            raise ActivityEndpointError(f"Garmin {operation} endpoint failed") from exc
        except Exception as exc:
            raise ActivityEndpointError(f"Garmin {operation} endpoint failed") from exc


class RecoveryProviderError(RuntimeError):
    """Base class for stable, secret-safe recovery provider failures."""


class RecoveryAuthenticationError(RecoveryProviderError):
    pass


class RecoveryEndpointError(RecoveryProviderError):
    pass


class InvalidRecoveryRequestError(RecoveryProviderError, ValueError):
    pass


class GarminRecoveryProvider:
    """Isolate unofficial Garmin recovery calls from MCP/application code."""

    def __init__(self, client_factory: Callable[[], GarminClient]) -> None:
        self._client_factory = client_factory

    def daily_statistics(self, day: str) -> NormalizedDailyStatistics:
        day = self._date(day)
        raw = self._call("daily statistics", lambda client: client.get_stats(day))
        return normalize_daily_statistics(raw, day)

    def heart_rate(self, day: str) -> NormalizedHeartRate:
        day = self._date(day)
        raw = self._call("heart-rate", lambda client: client.get_heart_rates(day))
        return normalize_heart_rate(raw, day)

    def sleep(self, day: str) -> NormalizedSleep:
        day = self._date(day)
        raw = self._call("sleep", lambda client: client.get_sleep_data(day))
        return normalize_sleep(raw, day)

    def hrv(self, day: str) -> NormalizedHRV:
        day = self._date(day)
        raw = self._call("HRV", lambda client: client.get_hrv_data(day))
        return normalize_hrv(raw, day)

    def hrv_range(self, start_date: str, end_date: str) -> list[NormalizedHRV]:
        start_date = self._date(start_date, name="start_date")
        end_date = self._date(end_date, name="end_date")
        start = date.fromisoformat(start_date)
        end = date.fromisoformat(end_date)
        if start > end:
            raise InvalidRecoveryRequestError(
                "start_date must be on or before end_date"
            )
        day_count = (end - start).days + 1
        if day_count > MAX_HRV_RANGE_DAYS:
            raise InvalidRecoveryRequestError(
                f"HRV ranges must contain at most {MAX_HRV_RANGE_DAYS} days"
            )
        raw = self._call(
            "HRV range",
            lambda client: client.get_hrv_data_range(start_date, end_date),
        )
        return normalize_hrv_range(raw)

    def body_battery(self, day: str) -> NormalizedBodyBattery:
        day = self._date(day)
        raw = self._call("Body Battery", lambda client: client.get_body_battery(day))
        return normalize_body_battery(raw, day)

    def stress(self, day: str) -> NormalizedStress:
        day = self._date(day)
        raw = self._call("stress", lambda client: client.get_stress_data(day))
        return normalize_stress(raw, day)

    @staticmethod
    def _date(value: Any, *, name: str = "date") -> str:
        try:
            return validate_date(value, name=name)
        except ValueError as exc:
            raise InvalidRecoveryRequestError(str(exc)) from exc

    def _call(self, operation: str, callback: Callable[[GarminClient], Any]) -> Any:
        try:
            return callback(self._client_factory())
        except GarminConnectAuthenticationError as exc:
            raise RecoveryAuthenticationError(
                "Garmin authentication failed; refresh the saved login"
            ) from exc
        except GarminConnectTooManyRequestsError as exc:
            raise RecoveryEndpointError(
                f"Garmin {operation} endpoint rate limit was reached"
            ) from exc
        except (GarminConnectConnectionError, GarminConnectNotFoundError) as exc:
            raise RecoveryEndpointError(f"Garmin {operation} endpoint failed") from exc
        except Exception as exc:
            raise RecoveryEndpointError(f"Garmin {operation} endpoint failed") from exc


class HeartRateZoneProviderError(RuntimeError):
    """Base class for stable, secret-safe zone-provider failures."""


class HeartRateZoneAuthenticationError(HeartRateZoneProviderError):
    pass


class HeartRateZoneEndpointError(HeartRateZoneProviderError):
    pass


class HeartRateZoneResponseError(HeartRateZoneProviderError):
    pass


class HeartRateZoneUnsupportedError(HeartRateZoneProviderError):
    pass


class GarminHeartRateZoneProvider:
    """Read and normalize configured running HR zones without profile data."""

    def __init__(self, client_factory: Callable[[], GarminClient]) -> None:
        self._client_factory = client_factory

    def running_zones(self) -> NormalizedHeartRateZones:
        try:
            client = self._client_factory()
            method = getattr(client, "get_heart_rate_zones", None)
            if method is None:
                raise HeartRateZoneUnsupportedError(
                    "Installed Garmin client does not support heart-rate-zone reads"
                )
            raw = method()
        except HeartRateZoneUnsupportedError:
            raise
        except GarminConnectAuthenticationError as exc:
            raise HeartRateZoneAuthenticationError(
                "Garmin authentication failed; refresh the saved login"
            ) from exc
        except GarminConnectTooManyRequestsError as exc:
            raise HeartRateZoneEndpointError(
                "Garmin heart-rate-zone endpoint rate limit was reached"
            ) from exc
        except (GarminConnectConnectionError, GarminConnectNotFoundError) as exc:
            raise HeartRateZoneEndpointError(
                "Garmin heart-rate-zone endpoint failed"
            ) from exc
        except Exception as exc:
            raise HeartRateZoneEndpointError(
                "Garmin heart-rate-zone endpoint failed"
            ) from exc
        try:
            return normalize_running_heart_rate_zones(raw)
        except MalformedHeartRateZoneResponseError as exc:
            raise HeartRateZoneResponseError(str(exc)) from exc


class WorkoutProviderError(RuntimeError):
    """Base class for stable, secret-safe workout provider failures."""


class WorkoutAuthenticationError(WorkoutProviderError):
    pass


class WorkoutEndpointError(WorkoutProviderError):
    pass


class WorkoutResponseError(WorkoutProviderError):
    pass


class WorkoutUnsupportedError(WorkoutProviderError):
    pass


class WorkoutNotFoundError(WorkoutProviderError):
    pass


class WorkoutUncertainResultError(WorkoutProviderError):
    pass


class InvalidWorkoutRequestError(WorkoutProviderError, ValueError):
    pass


def validate_workout_identifier(value: Any, *, name: str) -> str:
    valid = (
        isinstance(value, str)
        and value.isascii()
        and value.isdecimal()
        and not value.startswith("0")
        and len(value) <= 20
    )
    if not valid:
        raise InvalidWorkoutRequestError(
            f"{name} must be a positive numeric identifier"
        )
    return value


def validate_workout_date(value: Any, *, name: str) -> str:
    try:
        return validate_date(value, name=name)
    except ValueError as exc:
        raise InvalidWorkoutRequestError(str(exc)) from exc


class GarminWorkoutProvider:
    """Isolate unofficial Garmin workout and calendar calls from MCP code."""

    _write_guard = RLock()

    def __init__(self, client_factory: Callable[[], GarminClient]) -> None:
        self._client_factory = client_factory

    def create_running_workout(self, definition: WorkoutDefinition) -> dict[str, Any]:
        payload = serialize_running_workout(definition)

        def upload(client: GarminClient) -> Any:
            return self._invoke_write_method_once(
                client,
                "upload_workout",
                payload,
                unsupported_message=(
                    "Installed Garmin client does not support workout creation"
                ),
            )

        raw = self._call("workout creation", upload)
        workout_id = self._created_workout_id(raw, require_valid_identifier=False)
        aggregates = aggregate_workout(definition)
        return {
            "created": True,
            "workout_id": workout_id,
            "name": definition.name,
            "sport_type": definition.sport_type,
            "total_duration_s": aggregates["total_duration_s"],
            "total_distance_m": aggregates["total_distance_m"],
            "scheduled": False,
            "message": "Workout created in Garmin Connect but not scheduled.",
        }

    def create_and_schedule_running_workout(
        self, definition: WorkoutDefinition, scheduled_date: str
    ) -> dict[str, Any]:
        """Create one validated workout, then schedule only its returned ID."""
        scheduled_date = self._date(scheduled_date, name="scheduled_date")
        payload = serialize_running_workout(definition)
        aggregates = aggregate_workout(definition)

        def upload(client: GarminClient) -> Any:
            return self._invoke_write_method_once(
                client,
                "upload_workout",
                payload,
                unsupported_message=(
                    "Installed Garmin client does not support workout creation"
                ),
            )

        raw = self._write_once("workout creation", upload)
        workout_id = self._created_workout_id(raw, require_valid_identifier=True)

        base = {
            "created": True,
            "workout_id": workout_id,
            "scheduled": False,
            "already_scheduled": False,
            "scheduled_workout_id": None,
            "scheduled_date": scheduled_date,
            "name": definition.name,
            "sport_type": definition.sport_type,
            "total_duration_s": aggregates["total_duration_s"],
            "total_distance_m": aggregates["total_distance_m"],
        }
        try:
            schedule = self.schedule_existing_workout(workout_id, scheduled_date)
        except WorkoutProviderError as exc:
            return {
                **base,
                "partial_failure": True,
                "message": self._partial_schedule_failure_message(exc),
            }

        return {
            **base,
            "scheduled": schedule["scheduled"],
            "already_scheduled": schedule["already_scheduled"],
            "scheduled_workout_id": schedule["scheduled_workout_id"],
            "partial_failure": False,
            "message": (
                "Exactly one new workout was created and scheduled in Garmin Connect."
                if schedule["scheduled"]
                else "The new workout was created and was already assigned to the "
                "requested date; no additional schedule write occurred."
            ),
        }

    def _created_workout_id(self, raw: Any, *, require_valid_identifier: bool) -> str:
        try:
            normalized = normalize_workout(raw)
        except MalformedWorkoutResponseError as exc:
            raise WorkoutResponseError(str(exc)) from exc
        workout_id = normalized["workout_id"]
        if workout_id is None:
            raise WorkoutResponseError(
                "Garmin workout creation response did not include a workout ID"
            )
        if require_valid_identifier:
            return self._identifier(workout_id, name="workout_id", response=True)
        return workout_id

    @staticmethod
    def _partial_schedule_failure_message(exc: WorkoutProviderError) -> str:
        if isinstance(exc, WorkoutUncertainResultError):
            return (
                "Workout creation succeeded, but scheduling is uncertain. The new "
                "workout was preserved; inspect Garmin Connect before any further "
                "action."
            )
        if isinstance(exc, WorkoutAuthenticationError):
            reason = "Garmin authentication expired before scheduling"
        elif isinstance(exc, WorkoutUnsupportedError):
            reason = "the installed Garmin client cannot schedule workouts safely"
        elif isinstance(exc, WorkoutResponseError):
            reason = "Garmin returned a malformed scheduling response"
        elif isinstance(exc, WorkoutEndpointError):
            reason = (
                "the Garmin scheduling rate limit was reached"
                if "rate limit" in str(exc)
                else "the Garmin scheduling endpoint failed"
            )
        else:  # pragma: no cover - all current provider errors are covered above
            reason = "scheduling failed"
        return (
            f"Workout creation succeeded, but {reason}. The new unscheduled "
            "workout was preserved; no retry or cleanup occurred."
        )

    def schedule_existing_workout(
        self, workout_id: str, scheduled_date: str
    ) -> dict[str, Any]:
        """Schedule one existing template after an exact duplicate read."""
        workout_id = self._identifier(workout_id, name="workout_id")
        scheduled_date = self._date(scheduled_date, name="scheduled_date")

        existing = self.scheduled_workouts(scheduled_date, scheduled_date)
        duplicate = next(
            (
                item
                for item in existing
                if item["workout_id"] == workout_id
                and item["scheduled_date"] == scheduled_date
            ),
            None,
        )
        if duplicate is not None:
            scheduled_workout_id = duplicate["scheduled_workout_id"]
            if scheduled_workout_id is None:
                raise WorkoutResponseError(
                    "Existing Garmin schedule did not include a schedule ID"
                )
            scheduled_workout_id = self._identifier(
                scheduled_workout_id, name="scheduled_workout_id"
            )
            return {
                "scheduled": False,
                "already_scheduled": True,
                "scheduled_workout_id": scheduled_workout_id,
                "workout_id": workout_id,
                "scheduled_date": scheduled_date,
                "message": (
                    "No calendar change: this workout is already scheduled "
                    "on the requested date."
                ),
            }

        def schedule(client: GarminClient) -> Any:
            return self._invoke_write_method_once(
                client,
                "schedule_workout",
                workout_id,
                scheduled_date,
                unsupported_message=(
                    "Installed Garmin client does not support workout scheduling"
                ),
            )

        raw = self._write_once("workout scheduling", schedule)
        try:
            normalized = normalize_scheduled_workout(raw)
        except MalformedWorkoutResponseError as exc:
            raise WorkoutUncertainResultError(
                "Garmin scheduling result is uncertain; inspect Garmin Connect "
                "before any retry"
            ) from exc

        scheduled_workout_id = normalized["scheduled_workout_id"]
        if scheduled_workout_id is None:
            raise WorkoutUncertainResultError(
                "Garmin scheduling result is uncertain because no schedule ID "
                "was returned; inspect Garmin Connect before any retry"
            )
        scheduled_workout_id = self._identifier(
            scheduled_workout_id, name="scheduled_workout_id", response=True
        )
        response_workout_id = normalized["workout_id"]
        response_date = normalized["scheduled_date"]
        if response_workout_id is not None and response_workout_id != workout_id:
            raise WorkoutUncertainResultError(
                "Garmin scheduling returned an unexpected workout ID; inspect "
                "Garmin Connect before any retry"
            )
        if response_date is not None and response_date != scheduled_date:
            raise WorkoutUncertainResultError(
                "Garmin scheduling returned an unexpected calendar date; inspect "
                "Garmin Connect before any retry"
            )
        return {
            "scheduled": True,
            "already_scheduled": False,
            "scheduled_workout_id": scheduled_workout_id,
            "workout_id": workout_id,
            "scheduled_date": scheduled_date,
            "message": "Exactly one existing workout was scheduled in Garmin Connect.",
        }

    def scheduled_workout(
        self, scheduled_workout_id: str
    ) -> NormalizedScheduledWorkout:
        """Read one assignment by ID for a safe unscheduling preview."""
        scheduled_workout_id = self._identifier(
            scheduled_workout_id, name="scheduled_workout_id"
        )

        def read(client: GarminClient) -> Any:
            method = getattr(client, "get_scheduled_workout_by_id", None)
            if not callable(method):
                raise WorkoutUnsupportedError(
                    "Installed Garmin client does not support scheduled-workout lookup"
                )
            return method(scheduled_workout_id)

        raw = self._call("scheduled-workout lookup", read, not_found=True)
        try:
            normalized = normalize_scheduled_workout(raw)
        except MalformedWorkoutResponseError as exc:
            raise WorkoutResponseError(str(exc)) from exc
        returned_id = normalized["scheduled_workout_id"]
        if returned_id is None:
            raise WorkoutResponseError(
                "Garmin scheduled-workout response did not include a schedule ID"
            )
        returned_id = self._identifier(
            returned_id, name="scheduled_workout_id", response=True
        )
        if returned_id != scheduled_workout_id:
            raise WorkoutResponseError(
                "Garmin scheduled-workout response returned an unexpected schedule ID"
            )
        workout_id = normalized["workout_id"]
        scheduled_date = normalized["scheduled_date"]
        if workout_id is None or scheduled_date is None:
            raise WorkoutResponseError(
                "Garmin scheduled-workout response omitted assignment details"
            )
        self._identifier(workout_id, name="workout_id", response=True)
        return normalized

    def unschedule_existing_workout(self, scheduled_workout_id: str) -> dict[str, Any]:
        """Remove one verified calendar assignment without deleting its template."""
        scheduled_workout_id = self._identifier(
            scheduled_workout_id, name="scheduled_workout_id"
        )
        assignment = self.scheduled_workout(scheduled_workout_id)

        def unschedule(client: GarminClient) -> Any:
            return self._invoke_write_method_once(
                client,
                "unschedule_workout",
                scheduled_workout_id,
                unsupported_message=(
                    "Installed Garmin client does not support workout unscheduling"
                ),
            )

        self._write_once("workout unscheduling", unschedule)
        return {
            "unscheduled": True,
            "scheduled_workout_id": scheduled_workout_id,
            "workout_id": assignment["workout_id"],
            "scheduled_date": assignment["scheduled_date"],
            "workout_deleted": False,
            "message": (
                "Only the Garmin calendar assignment was removed; the workout "
                "template was not deleted."
            ),
        }

    def saved_workouts(
        self, *, start: int, limit: int, running_only: bool
    ) -> tuple[int, list[NormalizedWorkout]]:
        if isinstance(start, bool) or not isinstance(start, int) or start < 0:
            raise InvalidWorkoutRequestError("start must be a non-negative integer")
        if (
            isinstance(limit, bool)
            or not isinstance(limit, int)
            or not 1 <= limit <= MAX_WORKOUT_PAGE_SIZE
        ):
            raise InvalidWorkoutRequestError(
                f"limit must be between 1 and {MAX_WORKOUT_PAGE_SIZE}"
            )
        if not isinstance(running_only, bool):
            raise InvalidWorkoutRequestError("running_only must be a boolean")

        raw = self._call(
            "saved workouts",
            lambda client: client.connectapi(
                "/workout-service/workouts",
                params={
                    "start": start + 1,
                    "limit": limit,
                    "myWorkoutsOnly": "true",
                    "sharedWorkoutsOnly": "false",
                    "includeAtp": "false",
                    "orderBy": "UPDATE_DATE",
                    "orderSeq": "DESC",
                    **({"sportTypeKey": "running"} if running_only else {}),
                },
            ),
        )
        try:
            source_items = workout_items(raw)
            normalized = [normalize_workout(item) for item in source_items]
        except MalformedWorkoutResponseError as exc:
            raise WorkoutResponseError(str(exc)) from exc
        if running_only:
            normalized = [item for item in normalized if workout_is_running(item)]
        return len(source_items), normalized

    def scheduled_workouts(
        self, start_date: str, end_date: str
    ) -> list[NormalizedScheduledWorkout]:
        start_date = self._date(start_date, name="start_date")
        end_date = self._date(end_date, name="end_date")
        start = date.fromisoformat(start_date)
        end = date.fromisoformat(end_date)
        if start > end:
            raise InvalidWorkoutRequestError("start_date must be on or before end_date")
        day_count = (end - start).days + 1
        if day_count > MAX_SCHEDULED_WORKOUT_RANGE_DAYS:
            raise InvalidWorkoutRequestError(
                "scheduled-workout ranges must contain at most "
                f"{MAX_SCHEDULED_WORKOUT_RANGE_DAYS} days"
            )

        result: list[NormalizedScheduledWorkout] = []
        year, month = start.year, start.month
        while (year, month) <= (end.year, end.month):
            raw = self._call(
                "scheduled workouts",
                lambda client, year=year, month=month: client.get_scheduled_workouts(
                    year, month
                ),
            )
            try:
                normalized = [
                    normalize_scheduled_workout(item)
                    for item in scheduled_workout_items(raw)
                ]
            except MalformedWorkoutResponseError as exc:
                raise WorkoutResponseError(str(exc)) from exc
            for item in normalized:
                scheduled_date = item["scheduled_date"]
                if (
                    scheduled_date is not None
                    and start_date <= scheduled_date <= end_date
                ):
                    result.append(item)
            if month == 12:
                year, month = year + 1, 1
            else:
                month += 1

        result.sort(key=self._scheduled_sort_key)
        return result

    @staticmethod
    def _date(value: Any, *, name: str) -> str:
        return validate_workout_date(value, name=name)

    @staticmethod
    def _identifier(value: Any, *, name: str, response: bool = False) -> str:
        try:
            return validate_workout_identifier(value, name=name)
        except InvalidWorkoutRequestError as exc:
            if response:
                raise WorkoutResponseError(f"Garmin response {exc}") from exc
            raise

    @staticmethod
    def _scheduled_sort_key(
        item: NormalizedScheduledWorkout,
    ) -> tuple[str, str, str]:
        return (
            item["scheduled_date"] or "",
            item["scheduled_workout_id"] or "",
            item["workout_id"] or "",
        )

    def _call(
        self,
        operation: str,
        callback: Callable[[GarminClient], Any],
        *,
        not_found: bool = False,
    ) -> Any:
        try:
            return callback(self._client_factory())
        except WorkoutProviderError:
            raise
        except GarminConnectAuthenticationError as exc:
            raise WorkoutAuthenticationError(
                "Garmin authentication failed; refresh the saved login"
            ) from exc
        except GarminConnectTooManyRequestsError as exc:
            raise WorkoutEndpointError(
                f"Garmin {operation} endpoint rate limit was reached"
            ) from exc
        except GarminConnectNotFoundError as exc:
            if not_found:
                raise WorkoutNotFoundError(
                    "Garmin scheduled workout was not found"
                ) from exc
            raise WorkoutEndpointError(f"Garmin {operation} endpoint failed") from exc
        except GarminConnectConnectionError as exc:
            raise WorkoutEndpointError(f"Garmin {operation} endpoint failed") from exc
        except Exception as exc:
            raise WorkoutEndpointError(f"Garmin {operation} endpoint failed") from exc

    def _write_once(
        self, operation: str, callback: Callable[[GarminClient], Any]
    ) -> Any:
        """Invoke one write callback without provider-level retry or verification."""
        try:
            return callback(self._client_factory())
        except WorkoutProviderError:
            raise
        except GarminConnectAuthenticationError as exc:
            raise WorkoutAuthenticationError(
                "Garmin authentication failed; refresh the saved login"
            ) from exc
        except GarminConnectTooManyRequestsError as exc:
            raise WorkoutEndpointError(
                f"Garmin {operation} endpoint rate limit was reached"
            ) from exc
        except GarminConnectNotFoundError as exc:
            raise WorkoutEndpointError(f"Garmin {operation} endpoint failed") from exc
        except Exception as exc:
            raise WorkoutUncertainResultError(
                f"Garmin {operation} result is uncertain; inspect Garmin Connect "
                "before any retry"
            ) from exc

    @classmethod
    def _invoke_write_method_once(
        cls,
        client: GarminClient,
        method_name: str,
        *args: Any,
        unsupported_message: str,
    ) -> Any:
        """Block garminconnect's internal HTTP-401 replay for one write.

        Version 0.3.11's public schedule wrappers call the low-level client once,
        but that client normally refreshes authentication and repeats a request
        after a 401. The immediately preceding read already refreshes expiring
        credentials. During only the write call, fail closed if another refresh
        is requested so an HTTP request can never be replayed.
        """
        method = getattr(client, method_name, None)
        if not callable(method):
            raise WorkoutUnsupportedError(unsupported_message)

        transport = getattr(client, "client", None)
        refresh = getattr(transport, "_refresh_session", None)
        if transport is None or not callable(refresh):
            return method(*args)

        def block_write_replay() -> None:
            raise GarminConnectAuthenticationError(
                "Authentication refresh during a Garmin write is not replayed"
            )

        with cls._write_guard:
            instance_values = getattr(transport, "__dict__", None)
            if not isinstance(instance_values, dict):
                raise WorkoutUnsupportedError(
                    "Installed Garmin client cannot guarantee single-attempt writes"
                )
            had_override = "_refresh_session" in instance_values
            prior_override = instance_values.get("_refresh_session")
            transport._refresh_session = block_write_replay
            try:
                return method(*args)
            finally:
                if had_override:
                    transport._refresh_session = prior_override
                else:
                    del transport._refresh_session
