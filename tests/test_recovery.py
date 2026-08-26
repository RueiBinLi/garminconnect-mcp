from __future__ import annotations

import pytest

from garminconnect_mcp.recovery import (
    MalformedRecoveryResponseError,
    normalize_body_battery,
    normalize_daily_statistics,
    normalize_heart_rate,
    normalize_hrv,
    normalize_hrv_range,
    normalize_sleep,
    normalize_stress,
    validate_date,
)

DAY = "2030-04-12"


def test_validate_date_is_strict() -> None:
    assert validate_date(DAY) == DAY
    for invalid in (None, 20300412, "2030-4-12", "2030-02-30", "20300412"):
        with pytest.raises(ValueError, match="date"):
            validate_date(invalid)


def test_normalize_daily_statistics_uses_explicit_units() -> None:
    result = normalize_daily_statistics(
        {
            "calendarDate": DAY,
            "totalSteps": 4321,
            "dailyStepGoal": 8000,
            "totalDistanceMeters": 3456.7,
            "totalKilocalories": 2100,
            "activeKilocalories": 500,
            "bmrKilocalories": 1600,
            "activeSeconds": 1200,
            "highlyActiveSeconds": 300,
            "sedentarySeconds": 22000,
            "sleepingSeconds": 28000,
            "moderateIntensityMinutes": 12,
            "vigorousIntensityMinutes": 7,
            "restingHeartRate": 52,
            "minHeartRate": 45,
            "maxHeartRate": 165,
            "averageStressLevel": 31,
            "maxStressLevel": 74,
            "bodyBatteryChargedValue": 48,
            "bodyBatteryDrainedValue": 62,
            "bodyBatteryHighestValue": 81,
            "bodyBatteryLowestValue": 19,
            "ignoredLargeArray": [[1, 2]] * 100,
        },
        DAY,
    )

    assert result == {
        "date": DAY,
        "steps_count": 4321,
        "step_goal_count": 8000,
        "distance_m": 3456.7,
        "total_energy_kcal": 2100.0,
        "active_energy_kcal": 500.0,
        "resting_energy_kcal": 1600.0,
        "active_duration_s": 1200.0,
        "highly_active_duration_s": 300.0,
        "sedentary_duration_s": 22000.0,
        "sleeping_duration_s": 28000.0,
        "moderate_intensity_duration_s": 720.0,
        "vigorous_intensity_duration_s": 420.0,
        "resting_heart_rate_bpm": 52.0,
        "minimum_heart_rate_bpm": 45.0,
        "maximum_heart_rate_bpm": 165.0,
        "average_stress_native": 31.0,
        "maximum_stress_native": 74.0,
        "body_battery_charged_native": 48.0,
        "body_battery_drained_native": 62.0,
        "body_battery_highest_native": 81.0,
        "body_battery_lowest_native": 19.0,
    }


def test_normalize_heart_rate_discards_samples() -> None:
    assert normalize_heart_rate(
        {
            "calendarDate": DAY,
            "restingHeartRate": 51,
            "minHeartRate": 44,
            "maxHeartRate": 160,
            "lastSevenDaysAvgRestingHeartRate": 53,
            "heartRateValues": [[1, 50], [2, 51]],
        },
        DAY,
    ) == {
        "date": DAY,
        "resting_heart_rate_bpm": 51.0,
        "minimum_heart_rate_bpm": 44.0,
        "maximum_heart_rate_bpm": 160.0,
        "last_seven_days_average_resting_heart_rate_bpm": 53.0,
    }


def test_normalize_sleep_uses_seconds_utc_and_garmin_score_status() -> None:
    result = normalize_sleep(
        {
            "dailySleepDTO": {
                "calendarDate": DAY,
                "sleepStartTimestampGMT": 1902182400000,
                "sleepEndTimestampGMT": 1902211200000,
                "sleepTimeSeconds": 27000,
                "deepSleepSeconds": 4500,
                "lightSleepSeconds": 15000,
                "remSleepSeconds": 6000,
                "awakeSleepSeconds": 1500,
                "unmeasurableSleepSeconds": 0,
                "napTimeSeconds": 900,
                "sleepWindowConfirmationType": "ENHANCED_CONFIRMED_FINAL",
                "sleepScores": {"overall": {"value": 82, "qualifierKey": "GOOD"}},
            },
            "sleepMovement": [{"private": "discarded"}],
        },
        DAY,
    )

    assert result["total_sleep_duration_s"] == 27000.0
    assert result["deep_sleep_duration_s"] == 4500.0
    assert result["sleep_start_time_utc"].endswith("Z")
    assert result["sleep_score"] == 82.0
    assert result["sleep_score_status"] == "GOOD"
    assert result["sleep_window_status"] == "ENHANCED_CONFIRMED_FINAL"
    assert "sleepMovement" not in result


def test_normalize_hrv_single_and_range() -> None:
    summary = {
        "calendarDate": DAY,
        "weeklyAvg": 48,
        "lastNightAvg": 51,
        "lastNight5MinHigh": 79,
        "status": "BALANCED",
    }
    assert normalize_hrv({"hrvSummary": summary, "hrvReadings": [1, 2]}, DAY) == {
        "date": DAY,
        "weekly_average_ms": 48.0,
        "last_night_average_ms": 51.0,
        "last_night_five_minute_high_ms": 79.0,
        "status": "BALANCED",
    }
    assert normalize_hrv_range({"hrvSummaries": [summary]}) == [
        normalize_hrv({"hrvSummary": summary}, DAY)
    ]


def test_normalize_body_battery_uses_native_samples() -> None:
    assert normalize_body_battery(
        [
            {
                "date": DAY,
                "charged": 55,
                "drained": 42,
                "bodyBatteryValuesArray": [[1, 30], [2, 84], [3, 47]],
                "bodyBatteryActivityEvent": [{"private": "discarded"}],
            }
        ],
        DAY,
    ) == {
        "date": DAY,
        "charged_native": 55.0,
        "drained_native": 42.0,
        "highest_native": 84.0,
        "lowest_native": 30.0,
        "latest_native": 47.0,
    }


def test_normalize_stress_discards_samples() -> None:
    assert normalize_stress(
        {
            "calendarDate": DAY,
            "avgStressLevel": 28,
            "maxStressLevel": 72,
            "stressValuesArray": [[1, 25], [2, 30]],
        },
        DAY,
    ) == {
        "date": DAY,
        "average_stress_native": 28.0,
        "maximum_stress_native": 72.0,
    }


@pytest.mark.parametrize(
    ("normalizer", "missing"),
    [
        (normalize_daily_statistics, None),
        (normalize_heart_rate, {}),
        (normalize_sleep, None),
        (normalize_hrv, {}),
        (normalize_body_battery, []),
        (normalize_stress, None),
    ],
)
def test_missing_recovery_data_returns_explicit_nulls(normalizer, missing) -> None:
    result = normalizer(missing, DAY)

    assert result["date"] == DAY
    assert all(value is None for key, value in result.items() if key != "date")


@pytest.mark.parametrize(
    ("normalizer", "malformed"),
    [
        (normalize_daily_statistics, []),
        (normalize_heart_rate, {"unexpected": 1}),
        (normalize_sleep, {"dailySleepDTO": []}),
        (normalize_hrv, {"hrvSummary": []}),
        (normalize_body_battery, {}),
        (normalize_stress, "bad"),
    ],
)
def test_malformed_recovery_data_is_rejected(normalizer, malformed) -> None:
    with pytest.raises(MalformedRecoveryResponseError):
        normalizer(malformed, DAY)


def test_malformed_hrv_range_is_rejected() -> None:
    with pytest.raises(MalformedRecoveryResponseError):
        normalize_hrv_range({"hrvSummaries": {"not": "a list"}})
    with pytest.raises(MalformedRecoveryResponseError):
        normalize_hrv_range({"unexpected": []})
