from __future__ import annotations

from collections.abc import Callable
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

MAX_ACTIVITY_PAGE_SIZE = 100


class GarminClient(Protocol):
    def get_activities(
        self, start: int = 0, limit: int = 20, activitytype: str | None = None
    ) -> Any: ...

    def get_activity(self, activity_id: str) -> Any: ...


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
