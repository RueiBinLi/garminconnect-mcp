from __future__ import annotations

from typing import Any

import pytest
from garminconnect import (
    GarminConnectAuthenticationError,
    GarminConnectConnectionError,
    GarminConnectNotFoundError,
    GarminConnectTooManyRequestsError,
)

from garminconnect_mcp.activities import MalformedActivityResponseError
from garminconnect_mcp.provider import (
    ActivityAuthenticationError,
    ActivityEndpointError,
    ActivityNotFoundError,
    GarminActivityProvider,
    InvalidActivityRequestError,
)


class SyntheticClient:
    def __init__(self, response: Any = None, error: Exception | None = None) -> None:
        self.response = response
        self.error = error
        self.calls: list[tuple[str, tuple[object, ...], dict[str, object]]] = []

    def _result(self) -> Any:
        if self.error is not None:
            raise self.error
        return self.response

    def get_activities(
        self, start: int, limit: int, activitytype: str | None = None
    ) -> Any:
        self.calls.append(
            ("get_activities", (start, limit), {"activitytype": activitytype})
        )
        return self._result()

    def get_activity(self, activity_id: str) -> Any:
        self.calls.append(("get_activity", (activity_id,), {}))
        return self._result()


def provider(client: SyntheticClient) -> GarminActivityProvider:
    return GarminActivityProvider(lambda: client)


def test_recent_activities_has_bounded_pagination() -> None:
    client = SyntheticClient(response=[])

    assert (
        provider(client).recent_activities(start=10, limit=100, running_only=False)
        == []
    )
    assert client.calls == [("get_activities", (10, 100), {"activitytype": None})]

    for start, limit in [(-1, 5), (0, 0), (0, 101)]:
        with pytest.raises(InvalidActivityRequestError):
            provider(client).recent_activities(
                start=start, limit=limit, running_only=False
            )

    with pytest.raises(InvalidActivityRequestError, match="running_only"):
        provider(client).recent_activities(
            start=0,
            limit=5,
            running_only="yes",  # type: ignore[arg-type]
        )


def test_recent_activities_filters_running_at_endpoint_and_boundary() -> None:
    client = SyntheticClient(
        response=[
            {"activityId": 9000000010, "activityType": {"typeKey": "running"}},
            {"activityId": 9000000011, "activityType": {"typeKey": "cycling"}},
        ]
    )

    result = provider(client).recent_activities(start=0, limit=5, running_only=True)

    assert [activity["activity_id"] for activity in result] == ["9000000010"]
    assert client.calls == [("get_activities", (0, 5), {"activitytype": "running"})]


def test_activity_retrieves_one_normalized_summary() -> None:
    client = SyntheticClient(
        response={
            "activityId": 9000000012,
            "activityName": "Synthetic Easy Run",
            "activityTypeDTO": {"typeKey": "running"},
            "summaryDTO": {"distance": 6000, "duration": 1800},
        }
    )

    result = provider(client).activity(" 9000000012 ")

    assert result["activity_id"] == "9000000012"
    assert result["distance_m"] == 6000.0
    assert client.calls == [("get_activity", ("9000000012",), {})]


@pytest.mark.parametrize("activity_id", ["", "abc", "0", "-1"])
def test_activity_rejects_invalid_identifier(activity_id: str) -> None:
    with pytest.raises(InvalidActivityRequestError, match="positive numeric"):
        provider(SyntheticClient()).activity(activity_id)


@pytest.mark.parametrize(
    ("upstream_error", "expected_error", "message"),
    [
        (
            GarminConnectAuthenticationError("private upstream text"),
            ActivityAuthenticationError,
            "authentication failed",
        ),
        (
            GarminConnectConnectionError("private upstream text"),
            ActivityEndpointError,
            "endpoint failed",
        ),
        (
            GarminConnectTooManyRequestsError("private upstream text"),
            ActivityEndpointError,
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
        provider(SyntheticClient(error=upstream_error)).recent_activities(
            start=0, limit=5, running_only=False
        )

    assert "private upstream text" not in str(raised.value)


def test_provider_maps_unknown_activity() -> None:
    client = SyntheticClient(error=GarminConnectNotFoundError("private upstream text"))

    with pytest.raises(ActivityNotFoundError, match="was not found") as raised:
        provider(client).activity("9000000013")

    assert "private upstream text" not in str(raised.value)


def test_provider_preserves_malformed_response_category() -> None:
    with pytest.raises(MalformedActivityResponseError):
        provider(SyntheticClient(response={"unexpected": "shape"})).recent_activities(
            start=0, limit=5, running_only=False
        )
