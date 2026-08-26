from __future__ import annotations

from collections.abc import Callable
from datetime import date
from typing import Any, Protocol

from garminconnect import (
    GarminConnectAuthenticationError,
    GarminConnectConnectionError,
    GarminConnectNotFoundError,
    GarminConnectTooManyRequestsError,
)

from .activities import (
    NormalizedActivity,
    activity_is_running,
    activity_items,
    normalize_activity,
    normalized_activity_date,
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

    def get_scheduled_workouts(self, year: int, month: int) -> Any: ...

    def upload_workout(self, workout_json: dict[str, Any]) -> Any: ...


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
        normalized_id = activity_id.strip() if isinstance(activity_id, str) else ""
        if not normalized_id.isdecimal() or int(normalized_id) <= 0:
            raise InvalidActivityRequestError(
                "activity_id must be a positive numeric identifier"
            )

        raw = self._call(
            "activity details",
            lambda client: client.get_activity(normalized_id),
            not_found=True,
        )
        return normalize_activity(raw)

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


class InvalidWorkoutRequestError(WorkoutProviderError, ValueError):
    pass


class GarminWorkoutProvider:
    """Isolate unofficial Garmin workout and calendar calls from MCP code."""

    def __init__(self, client_factory: Callable[[], GarminClient]) -> None:
        self._client_factory = client_factory

    def create_running_workout(self, definition: WorkoutDefinition) -> dict[str, Any]:
        payload = serialize_running_workout(definition)

        def upload(client: GarminClient) -> Any:
            upload_workout = getattr(client, "upload_workout", None)
            if not callable(upload_workout):
                raise WorkoutUnsupportedError(
                    "Installed Garmin client does not support workout creation"
                )
            return upload_workout(payload)

        raw = self._call("workout creation", upload)
        try:
            normalized = normalize_workout(raw)
        except MalformedWorkoutResponseError as exc:
            raise WorkoutResponseError(str(exc)) from exc
        workout_id = normalized["workout_id"]
        if workout_id is None:
            raise WorkoutResponseError(
                "Garmin workout creation response did not include a workout ID"
            )
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
        try:
            return validate_date(value, name=name)
        except ValueError as exc:
            raise InvalidWorkoutRequestError(str(exc)) from exc

    @staticmethod
    def _scheduled_sort_key(
        item: NormalizedScheduledWorkout,
    ) -> tuple[str, str, str]:
        return (
            item["scheduled_date"] or "",
            item["scheduled_workout_id"] or "",
            item["workout_id"] or "",
        )

    def _call(self, operation: str, callback: Callable[[GarminClient], Any]) -> Any:
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
        except (GarminConnectConnectionError, GarminConnectNotFoundError) as exc:
            raise WorkoutEndpointError(f"Garmin {operation} endpoint failed") from exc
        except Exception as exc:
            raise WorkoutEndpointError(f"Garmin {operation} endpoint failed") from exc
