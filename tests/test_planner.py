from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from garminconnect_mcp.activities import NormalizedActivity
from garminconnect_mcp.heart_rate_zones import NormalizedHeartRateZones
from garminconnect_mcp.planner import (
    InvalidProposalRequestError,
    MalformedProposalDataError,
    ProposalConstraints,
    WeeklyProposalService,
    validate_proposal_request,
)
from garminconnect_mcp.recovery import NormalizedHRV
from garminconnect_mcp.workout_builder import WorkoutDefinition, aggregate_workout
from garminconnect_mcp.workouts import NormalizedScheduledWorkout


def activity(
    day: str, distance_m: float | None, duration_s: float | None
) -> NormalizedActivity:
    return {
        "activity_id": "synthetic",
        "start_time_local": f"{day} 06:00:00",
        "start_time_gmt": None,
        "activity_type": "running",
        "name": "Synthetic Run",
        "distance_m": distance_m,
        "duration_s": duration_s,
        "pace_s_per_km": None,
        "average_heart_rate_bpm": None,
        "maximum_heart_rate_bpm": None,
        "average_cadence_spm": None,
        "elevation_gain_m": None,
    }


def hrv(day: str, status: str | None = "balanced") -> NormalizedHRV:
    return {
        "date": day,
        "weekly_average_ms": None,
        "last_night_average_ms": None,
        "last_night_five_minute_high_ms": None,
        "status": status,
    }


class Reader:
    def __init__(self, result: Any, calls: list[tuple[Any, ...]], name: str):
        self.result = result
        self.calls = calls
        self.name = name

    def running_activities_by_date(self, start: str, end: str) -> list[Any]:
        self.calls.append((self.name, start, end))
        return self.result

    def hrv_range(self, start: str, end: str) -> list[Any]:
        self.calls.append((self.name, start, end))
        return self.result

    def scheduled_workouts(self, start: str, end: str) -> list[Any]:
        self.calls.append((self.name, start, end))
        return self.result

    def running_zones(self) -> NormalizedHeartRateZones:
        self.calls.append((self.name,))
        return self.result


def running_zones() -> NormalizedHeartRateZones:
    return {
        "sport": "running",
        "source_sport": "running",
        "training_method": "LTHR",
        "maximum_heart_rate_bpm": 190,
        "resting_heart_rate_bpm": 50,
        "lactate_threshold_heart_rate_bpm": 170,
        "zones": [
            {
                "zone": zone,
                "minimum_heart_rate_bpm": minimum,
                "maximum_heart_rate_bpm": maximum,
            }
            for zone, minimum, maximum in [
                (1, 100, 119),
                (2, 120, 139),
                (3, 140, 159),
                (4, 160, 174),
                (5, 175, 190),
            ]
        ],
    }


def service(
    activities: list[Any],
    recovery: list[Any] | None = None,
    scheduled: list[Any] | None = None,
) -> tuple[WeeklyProposalService, list[tuple[Any, ...]]]:
    calls: list[tuple[Any, ...]] = []
    return (
        WeeklyProposalService(
            lambda: Reader(activities, calls, "activities"),
            lambda: Reader(recovery or [], calls, "recovery"),
            lambda: Reader(scheduled or [], calls, "scheduled"),
            lambda: Reader(running_zones(), calls, "zones"),
        ),
        calls,
    )


def sufficient_history() -> list[NormalizedActivity]:
    return [
        activity("2030-03-05", 5000, 1800),
        activity("2030-03-07", 5000, 1800),
        activity("2030-03-12", 6000, 2100),
        activity("2030-03-14", 6000, 2100),
        activity("2030-03-19", 7000, 2400),
        activity("2030-03-21", 7000, 2400),
        activity("2030-03-26", 8000, 2700),
        activity("2030-03-28", 8000, 2700),
    ]


@pytest.mark.parametrize(
    "invalid",
    [
        "2030-04-02",
        "2030-4-01",
        "2030-04-01T00:00:00",
        "2030-04-01Z",
        "2030-04-01+08:00",
        ["2030-04-01"],
        20300401,
        None,
    ],
)
def test_week_start_is_strict_monday_before_reader_construction(invalid: Any) -> None:
    constructed = False

    def reader() -> Reader:
        nonlocal constructed
        constructed = True
        return Reader([], [], "unexpected")

    planner = WeeklyProposalService(reader, reader, reader, reader)
    with pytest.raises(InvalidProposalRequestError):
        planner.propose(invalid, {})
    assert constructed is False


@pytest.mark.parametrize(
    "constraints",
    [
        [],
        "{}",
        {},
        {"plan_start_date": "2030-03-04", "unknown": True},
        {"plan_start_date": "2030-03-04", "maximum_sessions": "3"},
        {"plan_start_date": "2030-03-04", "maximum_sessions": True},
        {"plan_start_date": "2030-03-04", "available_dates": "2030-04-01"},
        {
            "plan_start_date": "2030-03-04",
            "available_dates": ["2030-03-31"],
        },
        {
            "plan_start_date": "2030-03-04",
            "available_dates": ["2030-04-01", "2030-04-01"],
        },
        {"plan_start_date": "2030-03-04", "preferred_long_run_date": "2030-04-08"},
        {"plan_start_date": "2030-03-04", "user_note": " line break\n"},
        {"plan_start_date": "2030-03-04", "account": {"token": "private"}},
        {"plan_start_date": "2030-03-04", "workout_id": "123"},
        {"plan_start_date": "2030-03-05"},
        {"plan_start_date": "2030-04-08"},
        {"plan_start_date": "2030-3-04"},
        {"plan_start_date": "2030-03-04", "plan_type": "marathon"},
    ],
)
def test_constraints_reject_bulk_coercion_unknown_and_out_of_week(
    constraints: Any,
) -> None:
    with pytest.raises(InvalidProposalRequestError):
        validate_proposal_request("2030-04-01", constraints)


def test_constraints_model_rejects_unknown_fields_at_schema_boundary() -> None:
    with pytest.raises(ValidationError):
        ProposalConstraints.model_validate(
            {"plan_start_date": "2030-03-04", "url": "https://private.invalid"}
        )


def test_bounded_normalized_reads_and_deterministic_valid_output() -> None:
    recovery = [hrv(f"2030-03-{day:02}") for day in range(25, 32)]
    planner, calls = service(sufficient_history(), recovery)
    constraints = ProposalConstraints(
        plan_start_date="2030-03-04",
        available_dates=["2030-04-02", "2030-04-04", "2030-04-07"],
        maximum_sessions=3,
        preferred_long_run_date="2030-04-07",
        maximum_weekly_distance_m=12_000.0,
        user_note="Keep the week conservative.",
    )

    first = planner.propose("2030-04-01", constraints)
    second, _ = service(sufficient_history(), recovery)
    assert first == second.propose("2030-04-01", constraints)
    assert calls == [
        ("activities", "2030-03-04", "2030-03-31"),
        ("recovery", "2030-03-25", "2030-03-31"),
        ("scheduled", "2030-04-01", "2030-04-07"),
        ("zones",),
    ]
    assert first["rule_calculations"] == {
        "baseline_weekly_distance_m": 13000,
        "recovery_multiplier": 1.0,
        "distance_cap_m": 12000.0,
        "new_session_limit": 2,
        "new_distance_target_m": 12000,
        "long_run_share": 0.6,
    }
    assert [item["date"] for item in first["proposed_sessions"]] == [
        "2030-04-02",
        "2030-04-07",
    ]
    assert first["constraints"]["plan_week_number"] == 5
    assert [item["definition"]["name"] for item in first["proposed_sessions"]] == [
        "HM W05 - Easy 4.8K",
        "HM W05 - Long 7.2K",
    ]
    assert [
        item["aggregates"]["total_distance_m"] for item in first["proposed_sessions"]
    ] == [
        4800.0,
        7200.0,
    ]
    for proposed in first["proposed_sessions"]:
        definition = WorkoutDefinition.model_validate(
            proposed["definition"], strict=True
        )
        assert proposed["aggregates"] == aggregate_workout(definition)
        assert proposed["aggregates"]["distance_total_complete"] is True
        assert definition.steps[1].target is not None
        assert definition.steps[1].target.minimum_heart_rate_bpm == 120
        assert definition.steps[1].target.maximum_heart_rate_bpm == 139
    assert first["proposal_only"] is True
    assert first["created"] is False
    assert first["scheduled"] is False
    serialized = repr(first)
    for forbidden in ["workout_id", "scheduled_workout_id", "token", "url", "device"]:
        assert forbidden not in serialized.casefold()


def test_existing_running_commitment_is_compact_preserved_and_not_duplicated() -> None:
    commitment: NormalizedScheduledWorkout = {
        "scheduled_workout_id": "private-schedule-id",
        "scheduled_date": "2030-04-02",
        "workout_id": "private-workout-id",
        "name": "Existing Run",
        "sport_type": "running",
        "description": "private description",
        "estimated_duration_s": 1800,
        "estimated_distance_m": None,
    }
    planner, _ = service(sufficient_history(), scheduled=[commitment])
    result = planner.propose(
        "2030-04-01",
        {
            "plan_start_date": "2030-03-04",
            "available_dates": ["2030-04-02", "2030-04-04"],
            "maximum_sessions": 2,
        },
    )

    assert result["existing_scheduled_commitments"] == [
        {
            "date": "2030-04-02",
            "name": "Existing Run",
            "sport_type": "running",
            "estimated_duration_s": 1800,
            "estimated_distance_m": None,
            "preserved": True,
        }
    ]
    assert [item["date"] for item in result["proposed_sessions"]] == ["2030-04-04"]
    assert result["proposed_weekly_aggregates"]["distance_total_complete"] is False
    assert "private-schedule-id" not in repr(result)
    assert "private-workout-id" not in repr(result)
    assert "private description" not in repr(result)


def test_missing_and_insufficient_history_returns_normalized_state() -> None:
    planner, _ = service([activity("2030-03-25", None, 1200)])
    result = planner.propose("2030-04-01", {"plan_start_date": "2030-03-04"})

    assert result["factual_training_summary"]["history_sufficient"] is False
    assert result["factual_training_summary"]["baseline_weekly_distance_m"] is None
    assert result["proposed_sessions"] == []
    assert result["unavailable_inputs"] == [
        "Hard-session classification is unavailable from normalized inputs",
        "HRV records were unavailable for one or more lookback days",
        "HRV status was unavailable",
    ]
    assert "Insufficient history" in result["warnings"][0]


def test_recovery_rule_is_factual_conservative_and_non_medical() -> None:
    recovery = [hrv("2030-03-30", "LOW"), hrv("2030-03-31", "unbalanced")]
    planner, _ = service(sufficient_history(), recovery)
    result = planner.propose("2030-04-01", {"plan_start_date": "2030-03-04"})

    assert result["rule_calculations"]["recovery_multiplier"] == 0.9
    assert result["rule_calculations"]["new_distance_target_m"] == 11700
    warning = " ".join(result["warnings"]).casefold()
    assert "not a medical conclusion" in warning
    assert "illness" not in warning
    assert "injury" not in warning
    assert "overtraining" not in warning


def test_desired_sessions_overrides_baseline_but_not_maximum() -> None:
    planner, _ = service(sufficient_history())
    result = planner.propose(
        "2030-04-01",
        {
            "plan_start_date": "2030-03-04",
            "available_dates": [
                "2030-04-01",
                "2030-04-02",
                "2030-04-04",
                "2030-04-07",
            ],
            "desired_sessions": 4,
            "maximum_sessions": 4,
            "preferred_long_run_date": "2030-04-07",
        },
    )

    assert result["constraints"]["desired_sessions"] == 4
    assert result["rule_calculations"]["new_session_limit"] == 4
    assert len(result["proposed_sessions"]) == 4
    assert result["proposed_sessions"][-1]["purpose"] == "long_run"


def test_desired_sessions_must_not_exceed_maximum_before_readers() -> None:
    constructed = False

    def reader() -> Reader:
        nonlocal constructed
        constructed = True
        return Reader([], [], "unexpected")

    planner = WeeklyProposalService(reader, reader, reader, reader)
    with pytest.raises(InvalidProposalRequestError):
        planner.propose(
            "2030-04-01",
            {
                "plan_start_date": "2030-03-04",
                "desired_sessions": 4,
                "maximum_sessions": 3,
            },
        )
    assert constructed is False


def test_plan_week_must_not_precede_anchor_before_readers() -> None:
    constructed = False

    def reader() -> Reader:
        nonlocal constructed
        constructed = True
        return Reader([], [], "unexpected")

    planner = WeeklyProposalService(reader, reader, reader, reader)
    with pytest.raises(InvalidProposalRequestError, match="earlier"):
        planner.propose("2030-04-01", {"plan_start_date": "2030-04-08"})
    assert constructed is False


def test_malformed_normalized_data_maps_to_safe_error() -> None:
    planner, _ = service([{"raw": "secret upstream payload"}])
    with pytest.raises(MalformedProposalDataError) as raised:
        planner.propose("2030-04-01", {"plan_start_date": "2030-03-04"})
    assert str(raised.value) == "Normalized proposal input was malformed"
    assert "secret" not in str(raised.value)


def test_reader_interface_has_no_write_methods() -> None:
    assert (
        set(ActivityReaderMethod for ActivityReaderMethod in Reader.__dict__)
        & {
            "upload_workout",
            "create_running_workout",
            "schedule_workout",
            "unschedule_workout",
            "delete_workout",
            "push_workout",
        }
        == set()
    )
