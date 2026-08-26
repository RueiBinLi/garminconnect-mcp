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

MAX_ACTIVITY_PAGE_SIZE = 100
MAX_HRV_RANGE_DAYS = 14


class GarminClient(Protocol):
    def get_activities(
        self, start: int = 0, limit: int = 20, activitytype: str | None = None
    ) -> Any: ...

    def get_activity(self, activity_id: str) -> Any: ...

    def get_stats(self, cdate: str) -> Any: ...

    def get_heart_rates(self, cdate: str) -> Any: ...

    def get_sleep_data(self, cdate: str) -> Any: ...

    def get_hrv_data(self, cdate: str) -> Any: ...

    def get_hrv_data_range(self, start: str, end: str) -> Any: ...

    def get_body_battery(self, startdate: str, enddate: str | None = None) -> Any: ...

    def get_stress_data(self, cdate: str) -> Any: ...


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
