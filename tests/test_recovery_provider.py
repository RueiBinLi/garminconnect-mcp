from __future__ import annotations

from typing import Any

import pytest
from garminconnect import (
    GarminConnectAuthenticationError,
    GarminConnectConnectionError,
    GarminConnectTooManyRequestsError,
)

from garminconnect_mcp.provider import (
    GarminRecoveryProvider,
    InvalidRecoveryRequestError,
    RecoveryAuthenticationError,
    RecoveryEndpointError,
)
from garminconnect_mcp.recovery import MalformedRecoveryResponseError


class SyntheticRecoveryClient:
    def __init__(self, response: Any = None, error: Exception | None = None) -> None:
        self.response = response
        self.error = error
        self.calls: list[tuple[str, tuple[object, ...]]] = []

    def _result(self, name: str, *args: object) -> Any:
        self.calls.append((name, args))
        if self.error is not None:
            raise self.error
        return self.response

    def get_stats(self, day: str) -> Any:
        return self._result("get_stats", day)

    def get_heart_rates(self, day: str) -> Any:
        return self._result("get_heart_rates", day)

    def get_sleep_data(self, day: str) -> Any:
        return self._result("get_sleep_data", day)

    def get_hrv_data(self, day: str) -> Any:
        return self._result("get_hrv_data", day)

    def get_hrv_data_range(self, start: str, end: str) -> Any:
        return self._result("get_hrv_data_range", start, end)

    def get_body_battery(self, day: str, end: str | None = None) -> Any:
        return self._result("get_body_battery", day)

    def get_stress_data(self, day: str) -> Any:
        return self._result("get_stress_data", day)


def provider(client: SyntheticRecoveryClient) -> GarminRecoveryProvider:
    return GarminRecoveryProvider(lambda: client)


def test_recovery_provider_dispatches_each_read_only_endpoint() -> None:
    cases = [
        ("daily_statistics", {"calendarDate": "2030-04-12"}, "get_stats"),
        ("heart_rate", {"calendarDate": "2030-04-12"}, "get_heart_rates"),
        ("sleep", {"dailySleepDTO": None}, "get_sleep_data"),
        ("hrv", {"hrvSummary": None}, "get_hrv_data"),
        ("body_battery", [], "get_body_battery"),
        ("stress", {"calendarDate": "2030-04-12"}, "get_stress_data"),
    ]
    for method_name, response, endpoint in cases:
        client = SyntheticRecoveryClient(response=response)
        result = getattr(provider(client), method_name)("2030-04-12")
        assert result["date"] == "2030-04-12"
        assert client.calls == [(endpoint, ("2030-04-12",))]


@pytest.mark.parametrize("invalid", ["", "2030-4-12", "2030-02-30", "tomorrow"])
def test_recovery_provider_rejects_invalid_dates_before_call(invalid: str) -> None:
    client = SyntheticRecoveryClient()
    with pytest.raises(InvalidRecoveryRequestError):
        provider(client).daily_statistics(invalid)
    assert client.calls == []


def test_hrv_range_is_inclusive_ordered_and_bounded() -> None:
    client = SyntheticRecoveryClient(response={"hrvSummaries": []})
    assert provider(client).hrv_range("2030-04-01", "2030-04-14") == []
    assert client.calls == [("get_hrv_data_range", ("2030-04-01", "2030-04-14"))]

    for start, end in [
        ("2030-04-15", "2030-04-14"),
        ("2030-04-01", "2030-04-15"),
    ]:
        with pytest.raises(InvalidRecoveryRequestError):
            provider(SyntheticRecoveryClient()).hrv_range(start, end)


@pytest.mark.parametrize(
    ("upstream_error", "expected_error", "message"),
    [
        (
            GarminConnectAuthenticationError("private upstream text"),
            RecoveryAuthenticationError,
            "authentication failed",
        ),
        (
            GarminConnectConnectionError("private upstream text"),
            RecoveryEndpointError,
            "endpoint failed",
        ),
        (
            GarminConnectTooManyRequestsError("private upstream text"),
            RecoveryEndpointError,
            "rate limit",
        ),
    ],
)
def test_recovery_provider_maps_upstream_failures_to_safe_errors(
    upstream_error: Exception,
    expected_error: type[Exception],
    message: str,
) -> None:
    with pytest.raises(expected_error, match=message) as raised:
        provider(SyntheticRecoveryClient(error=upstream_error)).heart_rate("2030-04-12")
    assert "private upstream text" not in str(raised.value)


def test_recovery_provider_preserves_malformed_response_category() -> None:
    with pytest.raises(MalformedRecoveryResponseError):
        provider(SyntheticRecoveryClient(response={"unexpected": 1})).stress(
            "2030-04-12"
        )
