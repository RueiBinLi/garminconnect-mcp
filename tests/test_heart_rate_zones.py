from __future__ import annotations

from typing import Any

import pytest
from garminconnect import (
    GarminConnectAuthenticationError,
    GarminConnectConnectionError,
    GarminConnectTooManyRequestsError,
)

from garminconnect_mcp.heart_rate_zones import (
    MalformedHeartRateZoneResponseError,
    normalize_running_heart_rate_zones,
)
from garminconnect_mcp.provider import (
    GarminHeartRateZoneProvider,
    HeartRateZoneAuthenticationError,
    HeartRateZoneEndpointError,
    HeartRateZoneResponseError,
    HeartRateZoneUnsupportedError,
)


def raw_zones(sport: str = "RUNNING") -> dict[str, Any]:
    return {
        "sport": sport,
        "trainingMethod": "LTHR",
        "maxHeartRateUsed": 190,
        "restingHeartRateUsed": 50,
        "lactateThresholdHeartRateUsed": 170,
        "zone1Floor": 100,
        "zone2Floor": 120,
        "zone3Floor": 140,
        "zone4Floor": 160,
        "zone5Floor": 175,
        "privateProfileField": "discarded",
        "deviceId": "discarded",
    }


def test_normalizer_prefers_running_and_derives_contiguous_ranges() -> None:
    result = normalize_running_heart_rate_zones(
        [raw_zones("DEFAULT"), raw_zones("RUNNING")]
    )

    assert result == {
        "sport": "running",
        "source_sport": "running",
        "training_method": "LTHR",
        "maximum_heart_rate_bpm": 190,
        "resting_heart_rate_bpm": 50,
        "lactate_threshold_heart_rate_bpm": 170,
        "zones": [
            {
                "zone": 1,
                "minimum_heart_rate_bpm": 100,
                "maximum_heart_rate_bpm": 119,
            },
            {
                "zone": 2,
                "minimum_heart_rate_bpm": 120,
                "maximum_heart_rate_bpm": 139,
            },
            {
                "zone": 3,
                "minimum_heart_rate_bpm": 140,
                "maximum_heart_rate_bpm": 159,
            },
            {
                "zone": 4,
                "minimum_heart_rate_bpm": 160,
                "maximum_heart_rate_bpm": 174,
            },
            {
                "zone": 5,
                "minimum_heart_rate_bpm": 175,
                "maximum_heart_rate_bpm": 190,
            },
        ],
    }
    assert "private" not in repr(result).casefold()
    assert "device" not in repr(result).casefold()


def test_normalizer_explicitly_falls_back_to_default() -> None:
    result = normalize_running_heart_rate_zones([raw_zones("DEFAULT")])
    assert result["source_sport"] == "default"


@pytest.mark.parametrize(
    "raw",
    [
        None,
        {},
        [],
        ["bad"],
        [raw_zones("CYCLING")],
        [{**raw_zones(), "zone2Floor": None}],
        [{**raw_zones(), "zone3Floor": 110}],
        [{**raw_zones(), "maxHeartRateUsed": 170}],
    ],
)
def test_normalizer_rejects_malformed_or_unsupported_shapes(raw: Any) -> None:
    with pytest.raises(MalformedHeartRateZoneResponseError):
        normalize_running_heart_rate_zones(raw)


class Client:
    def __init__(self, result: Any = None, error: Exception | None = None) -> None:
        self.result = [raw_zones()] if result is None else result
        self.error = error
        self.calls = 0

    def get_heart_rate_zones(self) -> Any:
        self.calls += 1
        if self.error is not None:
            raise self.error
        return self.result


def test_provider_calls_only_dedicated_read_once() -> None:
    client = Client()
    result = GarminHeartRateZoneProvider(lambda: client).running_zones()
    assert result["zones"][1]["minimum_heart_rate_bpm"] == 120
    assert client.calls == 1


def test_provider_rejects_unsupported_client_without_raw_fallback() -> None:
    with pytest.raises(HeartRateZoneUnsupportedError, match="does not support"):
        GarminHeartRateZoneProvider(lambda: object()).running_zones()


@pytest.mark.parametrize(
    ("upstream", "expected", "message"),
    [
        (
            GarminConnectAuthenticationError("private upstream"),
            HeartRateZoneAuthenticationError,
            "authentication failed",
        ),
        (
            GarminConnectTooManyRequestsError("private upstream"),
            HeartRateZoneEndpointError,
            "rate limit",
        ),
        (
            GarminConnectConnectionError("private upstream"),
            HeartRateZoneEndpointError,
            "endpoint failed",
        ),
    ],
)
def test_provider_maps_upstream_errors_secret_safely(
    upstream: Exception, expected: type[Exception], message: str
) -> None:
    with pytest.raises(expected, match=message) as raised:
        GarminHeartRateZoneProvider(lambda: Client(error=upstream)).running_zones()
    assert "private upstream" not in str(raised.value)


def test_provider_maps_malformed_response() -> None:
    with pytest.raises(HeartRateZoneResponseError, match="malformed"):
        GarminHeartRateZoneProvider(lambda: Client(result={})).running_zones()
