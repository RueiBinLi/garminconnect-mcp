from __future__ import annotations

from datetime import date

import pytest

from garminconnect_mcp.activities import (
    MalformedActivityResponseError,
    activity_is_running,
    activity_items,
    normalize_activity,
    normalize_activity_splits,
    normalized_activity_date,
)


@pytest.fixture
def synthetic_run() -> dict[str, object]:
    return {
        "activityId": 9000000001,
        "startTimeLocal": "2030-04-12 06:30:00",
        "startTimeGMT": "2030-04-11 22:30:00",
        "activityType": {"typeKey": "trail_running"},
        "activityName": "Synthetic Trail Run",
        "distance": 10200,
        "duration": 3600,
        "averageSpeed": 2.5,
        "averageHR": 148,
        "maxHR": 171,
        "averageRunningCadenceInStepsPerMinute": 176,
        "elevationGain": 215.5,
        "ignoredPrivateNoise": {"large": [1, 2, 3]},
    }


def test_normalize_activity_preserves_compact_running_fields(
    synthetic_run: dict[str, object],
) -> None:
    assert normalize_activity(synthetic_run) == {
        "activity_id": "9000000001",
        "start_time_local": "2030-04-12 06:30:00",
        "start_time_gmt": "2030-04-11 22:30:00",
        "activity_type": "trail_running",
        "name": "Synthetic Trail Run",
        "distance_m": 10200.0,
        "duration_s": 3600.0,
        "pace_s_per_km": 400.0,
        "average_heart_rate_bpm": 148.0,
        "maximum_heart_rate_bpm": 171.0,
        "average_cadence_spm": 176.0,
        "elevation_gain_m": 215.5,
    }


def test_normalize_activity_reads_summary_detail_envelope() -> None:
    result = normalize_activity(
        {
            "activityId": 9000000002,
            "activityName": "Synthetic Detail",
            "activityTypeDTO": {"typeKey": "running"},
            "summaryDTO": {
                "startTimeLocal": "2030-04-13 07:15:00",
                "distance": 8000,
                "duration": 2400,
                "averageSpeed": 3.2,
                "averageRunCadence": 174,
            },
        }
    )

    assert result["activity_id"] == "9000000002"
    assert result["activity_type"] == "running"
    assert result["distance_m"] == 8000.0
    assert result["pace_s_per_km"] == 312.5
    assert result["average_cadence_spm"] == 174.0


def test_normalize_activity_represents_unavailable_fields_as_none() -> None:
    result = normalize_activity({"activityId": 9000000003})

    assert result["activity_id"] == "9000000003"
    assert all(value is None for key, value in result.items() if key != "activity_id")


def test_normalize_activity_does_not_derive_pace_without_average_speed() -> None:
    result = normalize_activity(
        {"activityId": 9000000004, "distance": 5000, "duration": 1500}
    )

    assert result["pace_s_per_km"] is None


@pytest.mark.parametrize("raw", [None, [], {}, {"unexpected": "shape"}])
def test_normalize_activity_rejects_malformed_response(raw: object) -> None:
    with pytest.raises(MalformedActivityResponseError, match="activity response"):
        normalize_activity(raw)


def test_activity_items_supports_list_and_known_envelope() -> None:
    items = [{"activityId": 9000000005}]

    assert activity_items(items) is items
    assert activity_items({"activities": items}) is items


@pytest.mark.parametrize("raw", [None, {}, {"activities": {}}, ["bad item"]])
def test_activity_items_rejects_malformed_response(raw: object) -> None:
    with pytest.raises(
        MalformedActivityResponseError, match="recent-activities response"
    ):
        activity_items(raw)


def test_activity_is_running_recognizes_running_variants(
    synthetic_run: dict[str, object],
) -> None:
    assert activity_is_running(normalize_activity(synthetic_run)) is True
    assert (
        activity_is_running(
            normalize_activity(
                {"activityId": 9000000006, "activityType": {"typeKey": "cycling"}}
            )
        )
        is False
    )


def test_normalized_activity_date_prefers_local_and_handles_unavailable() -> None:
    activity = normalize_activity(
        {
            "activityId": 9000000007,
            "startTimeLocal": "2030-04-12 06:30:00",
            "startTimeGMT": "2030-04-11 22:30:00",
        }
    )

    assert normalized_activity_date(activity) == date(2030, 4, 12)
    activity["start_time_local"] = "malformed"
    assert normalized_activity_date(activity) == date(2030, 4, 11)
    activity["start_time_gmt"] = None
    assert normalized_activity_date(activity) is None


def test_normalize_activity_splits_preserves_recorded_laps_and_partial_final() -> None:
    result = normalize_activity_splits(
        {
            "activityId": 9000000100,
            "lapDTOs": [
                {
                    "lapIndex": 1,
                    "startTimeLocal": "2030-04-12 06:00:00",
                    "distance": 1000,
                    "duration": 310,
                    "movingDuration": 300,
                    "elapsedDuration": 315,
                    "averageSpeed": 9.9,
                    "averageMovingSpeed": 3.333333333,
                    "averageHR": 145,
                    "maxHR": 152,
                    "averageRunCadence": 170,
                    "elevationGain": 4,
                    "elevationLoss": 3,
                    "intensityType": "ACTIVE",
                    "privateRawField": "discard me",
                },
                {"lapIndex": 2, "distance": 437.2, "movingDuration": 140},
            ],
        },
        activity_id="9000000100",
    )

    assert result == {
        "activity_id": "9000000100",
        "split_type": "lap",
        "splits": [
            {
                "split_index": 1,
                "start_time_local": "2030-04-12 06:00:00",
                "distance_m": 1000.0,
                "duration_s": 310.0,
                "moving_duration_s": 300.0,
                "elapsed_duration_s": 315.0,
                "pace_s_per_km": 300.0,
                "average_heart_rate_bpm": 145.0,
                "maximum_heart_rate_bpm": 152.0,
                "average_cadence_spm": 170.0,
                "elevation_gain_m": 4.0,
                "elevation_loss_m": 3.0,
                "intensity_type": "ACTIVE",
            },
            {
                "split_index": 2,
                "start_time_local": None,
                "distance_m": 437.2,
                "duration_s": None,
                "moving_duration_s": 140.0,
                "elapsed_duration_s": None,
                "pace_s_per_km": None,
                "average_heart_rate_bpm": None,
                "maximum_heart_rate_bpm": None,
                "average_cadence_spm": None,
                "elevation_gain_m": None,
                "elevation_loss_m": None,
                "intensity_type": None,
            },
        ],
    }


@pytest.mark.parametrize("raw", [{}, {"lapDTOs": []}, {"lapDTOs": [None]}])
def test_normalize_activity_splits_rejects_malformed_or_empty(raw: object) -> None:
    with pytest.raises(MalformedActivityResponseError, match="activity|laps"):
        normalize_activity_splits(raw, activity_id="9000000101")
