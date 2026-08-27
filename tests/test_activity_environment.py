from __future__ import annotations

import math

import pytest

from garminconnect_mcp.activity_environment import (
    MalformedActivityTemperatureResponseError,
    MalformedActivityWeatherResponseError,
    normalize_activity_temperature,
    normalize_activity_weather,
)


def temperature_details(values: list[object]) -> dict[str, object]:
    return {
        "metricDescriptors": [
            {"key": "directTimestamp", "metricsIndex": 0},
            {"key": "directAirTemperature", "metricsIndex": 2},
        ],
        "activityDetailMetrics": [
            {"metrics": [index * 60, "ignored", value]}
            for index, value in enumerate(values)
        ],
    }


def test_temperature_summary_uses_arithmetic_celsius_statistics() -> None:
    result = normalize_activity_temperature(
        temperature_details([18, 20, 25]), activity_id="9000000200"
    )

    assert result == {
        "activity_id": "9000000200",
        "average_temperature_c": 21.0,
        "minimum_temperature_c": 18.0,
        "maximum_temperature_c": 25.0,
        "sample_count": 3,
        "source": "garmin_activity_detail_directAirTemperature",
        "warnings": [],
    }


def test_temperature_summary_resolves_descriptor_instead_of_fixed_index() -> None:
    raw = {
        "metricDescriptors": [
            {"key": "directAirTemperature", "metricsIndex": 0},
            {"key": "directTimestamp", "metricsIndex": 1},
        ],
        "activityDetailMetrics": [
            {"metrics": [15.5, 0]},
            {"metrics": [16.5, 60]},
        ],
    }

    result = normalize_activity_temperature(raw, activity_id="9000000201")

    assert result["average_temperature_c"] == 16.0
    assert result["minimum_temperature_c"] == 15.5
    assert result["maximum_temperature_c"] == 16.5


def test_temperature_summary_returns_unavailable_when_channel_is_missing() -> None:
    result = normalize_activity_temperature(
        {
            "metricDescriptors": [{"key": "directTimestamp", "metricsIndex": 0}],
            "activityDetailMetrics": [{"metrics": [0]}],
        },
        activity_id="9000000202",
    )

    assert result["average_temperature_c"] is None
    assert result["minimum_temperature_c"] is None
    assert result["maximum_temperature_c"] is None
    assert result["sample_count"] == 0
    assert result["warnings"] == [
        "Garmin activity details contained no valid directAirTemperature samples"
    ]


@pytest.mark.parametrize(
    "values",
    [
        [None, None],
        ["18", object()],
        [math.nan, math.inf, -math.inf],
    ],
)
def test_temperature_summary_ignores_unusable_samples(values: list[object]) -> None:
    result = normalize_activity_temperature(
        temperature_details(values), activity_id="9000000203"
    )

    assert result["sample_count"] == 0
    assert result["average_temperature_c"] is None


def test_temperature_summary_ignores_invalid_samples_beside_valid_samples() -> None:
    result = normalize_activity_temperature(
        temperature_details([20, None, "21", math.nan, 22]),
        activity_id="9000000204",
    )

    assert result["average_temperature_c"] == 21.0
    assert result["sample_count"] == 2
    assert result["warnings"] == ["Ignored 3 invalid directAirTemperature samples"]


@pytest.mark.parametrize(
    "raw",
    [
        None,
        [],
        {},
        {"metricDescriptors": {}, "activityDetailMetrics": []},
        {"metricDescriptors": [None], "activityDetailMetrics": []},
        {"metricDescriptors": [], "activityDetailMetrics": [None]},
        {"metricDescriptors": [], "activityDetailMetrics": [{}]},
    ],
)
def test_temperature_summary_rejects_malformed_details(raw: object) -> None:
    with pytest.raises(MalformedActivityTemperatureResponseError):
        normalize_activity_temperature(raw, activity_id="9000000205")


def test_weather_observation_normalizes_complete_response_without_unit_claims() -> None:
    result = normalize_activity_weather(
        {
            "issueDate": "2030-04-12T06:15:00+08:00",
            "temp": 24,
            "apparentTemp": 26,
            "dewPoint": 20,
            "relativeHumidity": 78,
            "windSpeed": 9,
            "windGust": 14,
            "windDirection": 180,
            "windDirectionCompassPoint": "S",
            "weatherTypeDTO": {
                "desc": "Synthetic Partly Cloudy",
                "weatherTypePk": 3,
                "private": "discarded",
            },
            "weatherStationDTO": {
                "name": "Synthetic Private Station",
                "timezone": "Asia/Example",
                "latitude": 1.0,
                "longitude": 2.0,
            },
            "latitude": 3.0,
            "longitude": 4.0,
        },
        activity_id="9000000210",
    )

    assert result == {
        "activity_id": "9000000210",
        "observed_at": "2030-04-12T06:15:00+08:00",
        "temperature": 24.0,
        "apparent_temperature": 26.0,
        "dew_point": 20.0,
        "relative_humidity_pct": 78.0,
        "wind_speed": 9.0,
        "wind_gust": 14.0,
        "wind_direction": 180.0,
        "wind_direction_compass_point": "S",
        "weather_condition": "Synthetic Partly Cloudy",
        "weather_condition_id": "3",
        "weather_station_present": True,
        "weather_station_timezone": "Asia/Example",
        "source": "garmin_activity_weather_station",
        "units_verified": False,
    }
    assert "weather_station_name" not in result
    assert "latitude" not in result
    assert "longitude" not in result


def test_weather_observation_normalizes_null_filled_and_missing_responses() -> None:
    for raw in (
        {
            "issueDate": None,
            "temp": None,
            "apparentTemp": None,
            "dewPoint": None,
            "relativeHumidity": None,
            "windSpeed": None,
            "windGust": None,
            "windDirection": None,
            "windDirectionCompassPoint": None,
            "weatherTypeDTO": None,
            "weatherStationDTO": None,
        },
        {},
    ):
        result = normalize_activity_weather(raw, activity_id="9000000211")

        assert result["observed_at"] is None
        assert result["temperature"] is None
        assert result["relative_humidity_pct"] is None
        assert result["weather_condition"] is None
        assert result["weather_condition_id"] is None
        assert result["weather_station_present"] is False
        assert result["units_verified"] is False


def test_weather_observation_handles_malformed_nested_structures() -> None:
    result = normalize_activity_weather(
        {
            "weatherTypeDTO": "unexpected",
            "weatherStationDTO": ["unexpected"],
        },
        activity_id="9000000212",
    )

    assert result["weather_condition"] is None
    assert result["weather_condition_id"] is None
    assert result["weather_station_present"] is False
    assert result["weather_station_timezone"] is None


@pytest.mark.parametrize("issue_date", ["2030-04-12T06:15:00", "not-a-date", 1])
def test_weather_observation_rejects_unverified_timestamp_shapes(
    issue_date: object,
) -> None:
    result = normalize_activity_weather(
        {"issueDate": issue_date}, activity_id="9000000213"
    )

    assert result["observed_at"] is None


@pytest.mark.parametrize("raw", [None, [], "bad"])
def test_weather_observation_rejects_malformed_top_level(raw: object) -> None:
    with pytest.raises(MalformedActivityWeatherResponseError):
        normalize_activity_weather(raw, activity_id="9000000214")


def test_weather_observation_ignores_unexpected_and_non_finite_numbers() -> None:
    result = normalize_activity_weather(
        {
            "temp": "24",
            "apparentTemp": True,
            "dewPoint": math.nan,
            "relativeHumidity": math.inf,
            "windSpeed": -math.inf,
        },
        activity_id="9000000215",
    )

    assert result["temperature"] is None
    assert result["apparent_temperature"] is None
    assert result["dew_point"] is None
    assert result["relative_humidity_pct"] is None
    assert result["wind_speed"] is None
