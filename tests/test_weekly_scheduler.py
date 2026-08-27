from __future__ import annotations

import copy
from typing import Any

import pytest

from garminconnect_mcp.planner import InvalidProposalRequestError
from garminconnect_mcp.provider import (
    WorkoutAuthenticationError,
    WorkoutEndpointError,
    WorkoutResponseError,
    WorkoutUncertainResultError,
    WorkoutUnsupportedError,
)
from garminconnect_mcp.weekly_scheduler import (
    ApprovalStore,
    ExpiredWeeklyPlanApprovalError,
    InvalidWeeklyPlanApprovalError,
    MalformedWeeklyPlanError,
    StaleWeeklyPlanError,
    WeeklyPlanConflictError,
    WeeklyPlanSchedulingService,
    proposal_fingerprint,
)
from garminconnect_mcp.workout_builder import WorkoutDefinition, aggregate_workout
from garminconnect_mcp.workouts import NormalizedScheduledWorkout


def definition(name: str, distance_m: float) -> dict[str, Any]:
    model = WorkoutDefinition.model_validate(
        {
            "sport_type": "running",
            "name": name,
            "description": "Synthetic weekly scheduling fixture.",
            "steps": [
                {
                    "step_type": "warmup",
                    "duration": {
                        "duration_type": "distance",
                        "distance_m": distance_m * 0.1,
                    },
                    "target": {"target_type": "none"},
                },
                {
                    "step_type": "run",
                    "duration": {
                        "duration_type": "distance",
                        "distance_m": distance_m * 0.8,
                    },
                    "target": {
                        "target_type": "heart_rate_range",
                        "minimum_heart_rate_bpm": 120,
                        "maximum_heart_rate_bpm": 139,
                    },
                },
                {
                    "step_type": "cooldown",
                    "duration": {
                        "duration_type": "distance",
                        "distance_m": distance_m * 0.1,
                    },
                    "target": {"target_type": "none"},
                },
            ],
        },
        strict=True,
    )
    return model.model_dump(mode="json")


def proposal(session_count: int = 2) -> dict[str, Any]:
    dates = ["2030-04-02", "2030-04-04", "2030-04-06"][:session_count]
    sessions: list[dict[str, Any]] = []
    for order, day in enumerate(dates, start=1):
        workout = definition(f"HM W05 - Synthetic {order}", 5000 + order * 1000)
        model = WorkoutDefinition.model_validate(workout, strict=True)
        sessions.append(
            {
                "date": day,
                "purpose": "long_run" if order == session_count else "easy_run",
                "definition": workout,
                "execution_order": order,
                "aggregates": aggregate_workout(model),
            }
        )
    return {
        "week_start": "2030-04-01",
        "week_end": "2030-04-07",
        "factual_training_summary": {"baseline_weekly_distance_m": 12_000},
        "factual_heart_rate_zone_summary": {
            "zone2_minimum_heart_rate_bpm": 120,
            "zone2_maximum_heart_rate_bpm": 139,
        },
        "constraints": {
            "plan_start_date": "2030-03-04",
            "desired_sessions": session_count,
            "maximum_sessions": session_count,
        },
        "existing_scheduled_commitments": [],
        "rules_applied": ["Synthetic deterministic rule."],
        "rule_calculations": {"new_session_limit": session_count},
        "warnings": [],
        "unavailable_inputs": [],
        "proposed_sessions": sessions,
        "proposed_weekly_aggregates": {"new_session_count": session_count},
        "proposal_only": True,
        "created": False,
        "scheduled": False,
        "message": "Proposal only: no Garmin workout or calendar change occurred.",
    }


def scheduled(
    day: str = "2030-04-03",
    *,
    schedule_id: str = "8001",
    workout_id: str = "7001",
) -> NormalizedScheduledWorkout:
    return {
        "scheduled_workout_id": schedule_id,
        "scheduled_date": day,
        "workout_id": workout_id,
        "name": "Synthetic Existing Run",
        "sport_type": "running",
        "description": None,
        "estimated_duration_s": 1800.0,
        "estimated_distance_m": 5000.0,
    }


class Planner:
    def __init__(
        self,
        result: dict[str, Any],
        calendar: list[NormalizedScheduledWorkout],
        calls: list[Any],
    ) -> None:
        self.result = result
        self.calendar = calendar
        self.calls = calls

    def propose_with_calendar_snapshot(
        self, week_start: str, constraints: Any
    ) -> tuple[dict[str, Any], list[NormalizedScheduledWorkout]]:
        self.calls.append(("propose", week_start, constraints))
        return copy.deepcopy(self.result), copy.deepcopy(self.calendar)


class Reader:
    def __init__(self, state: dict[str, Any], calls: list[Any]) -> None:
        self.state = state
        self.calls = calls

    def scheduled_workouts(
        self, start_date: str, end_date: str
    ) -> list[NormalizedScheduledWorkout]:
        self.calls.append(("calendar", start_date, end_date))
        error = self.state.get("error")
        if error is not None:
            raise error
        return copy.deepcopy(self.state["calendar"])


class Writer:
    def __init__(self, outcomes: list[Any], calls: list[Any]) -> None:
        self.outcomes = outcomes
        self.calls = calls

    def create_and_schedule_running_workout(
        self, workout: WorkoutDefinition, scheduled_date: str
    ) -> dict[str, Any]:
        self.calls.append(("write", workout.name, scheduled_date))
        write_count = len([item for item in self.calls if item[0] == "write"])
        outcome = self.outcomes[write_count - 1]
        if isinstance(outcome, Exception):
            raise outcome
        return copy.deepcopy(outcome)


def success() -> dict[str, Any]:
    return {
        "created": True,
        "scheduled": True,
        "workout_id": "private-workout-id",
        "scheduled_workout_id": "private-schedule-id",
        "partial_failure": False,
        "message": "Synthetic success.",
    }


def service(
    *,
    plan: dict[str, Any] | None = None,
    preview_calendar: list[NormalizedScheduledWorkout] | None = None,
    fresh_calendar: list[NormalizedScheduledWorkout] | None = None,
    outcomes: list[Any] | None = None,
    token: str = "A" * 43,
) -> tuple[WeeklyPlanSchedulingService, list[Any], dict[str, Any]]:
    calls: list[Any] = []
    state: dict[str, Any] = {"calendar": fresh_calendar or []}
    source = plan or proposal()
    store = ApprovalStore(token_factory=lambda: token)
    result = WeeklyPlanSchedulingService(
        lambda: Planner(source, preview_calendar or [], calls),  # type: ignore[arg-type]
        lambda: Reader(state, calls),
        lambda: Writer(outcomes or [success(), success()], calls),
        store,
    )
    return result, calls, state


def preview(service: WeeklyPlanSchedulingService) -> dict[str, Any]:
    return service.preview(
        "2030-04-01",
        {
            "plan_start_date": "2030-03-04",
            "desired_sessions": 2,
            "maximum_sessions": 2,
        },
    )


def test_invalid_preview_request_fails_before_service_construction() -> None:
    constructed = False

    def construct() -> Any:
        nonlocal constructed
        constructed = True
        raise AssertionError

    scheduling = WeeklyPlanSchedulingService(
        construct, construct, construct, ApprovalStore()
    )
    with pytest.raises(InvalidProposalRequestError):
        scheduling.preview("2030-04-01T00:00:00", {"plan_start_date": "2030-03-04"})
    assert constructed is False


def test_preview_is_exact_read_only_approval_envelope() -> None:
    scheduling, calls, _ = service()
    result = preview(scheduling)

    assert result["preview_only"] is True
    assert result["created"] is False
    assert result["scheduled"] is False
    assert result["intended_creation_count"] == 2
    assert result["intended_schedule_count"] == 2
    assert [item["execution_order"] for item in result["intended_garmin_writes"]] == [
        1,
        2,
    ]
    assert result["proposal_fingerprint"].startswith("sha256:")
    assert result["approval_token"] == "A" * 43
    assert [item[0] for item in calls] == ["propose"]


def test_unconfirmed_call_is_fully_offline_and_does_not_consume_approval() -> None:
    scheduling, calls, _ = service()
    reviewed = preview(scheduling)
    calls.clear()

    first = scheduling.schedule(
        reviewed["approval_token"], reviewed["proposal_fingerprint"], confirmed=False
    )
    second = scheduling.schedule(
        reviewed["approval_token"], reviewed["proposal_fingerprint"], confirmed=False
    )

    assert first == second
    assert first["preview_only"] is True
    assert first["remaining_sessions_not_attempted"] == 2
    assert calls == []


@pytest.mark.parametrize(
    ("token", "fingerprint", "confirmed"),
    [
        (["token"], "sha256:" + "0" * 64, False),
        ("https://invalid.example", "sha256:" + "0" * 64, False),
        ("1", "sha256:" + "0" * 64, False),
        ("A" * 43, {"raw": "json"}, False),
        ("A" * 43, "0" * 64, False),
        ("A" * 43, "sha256:" + "0" * 64, "true"),
        ("A" * 43, "sha256:" + "0" * 64, 1),
    ],
)
def test_schedule_rejects_arrays_urls_json_and_coercible_confirmation(
    token: Any, fingerprint: Any, confirmed: Any
) -> None:
    scheduling, calls, _ = service()
    with pytest.raises(InvalidWeeklyPlanApprovalError):
        scheduling.schedule(token, fingerprint, confirmed=confirmed)
    assert calls == []


def test_fingerprint_changes_with_every_reviewed_value() -> None:
    original = proposal()
    material = {
        "proposal": original,
        "intended_garmin_writes": WeeklyPlanSchedulingService._intended_writes(
            original
        ),
    }
    expected = proposal_fingerprint(material)
    assert proposal_fingerprint(copy.deepcopy(material)) == expected

    mutations = [
        lambda value: value["proposal"]["factual_training_summary"].update(
            baseline_weekly_distance_m=12_100
        ),
        lambda value: value["proposal"]["constraints"].update(desired_sessions=1),
        lambda value: value["proposal"]["existing_scheduled_commitments"].append(
            {"date": "2030-04-03", "preserved": True}
        ),
        lambda value: value["proposal"]["proposed_sessions"][0].update(
            date="2030-04-03"
        ),
        lambda value: value["proposal"]["proposed_sessions"][0]["definition"].update(
            name="Changed"
        ),
        lambda value: value["proposal"]["proposed_sessions"][0]["definition"]["steps"][
            1
        ]["duration"].update(distance_m=1),
        lambda value: value["proposal"]["proposed_sessions"][0]["definition"]["steps"][
            1
        ]["duration"].update(duration_type="time"),
        lambda value: value["proposal"]["proposed_sessions"][0]["definition"]["steps"][
            1
        ]["target"].update(maximum_heart_rate_bpm=140),
        lambda value: value["proposal"]["proposed_sessions"][0]["aggregates"].update(
            known_distance_m=1
        ),
        lambda value: value["intended_garmin_writes"][0].update(execution_order=2),
    ]
    for mutate in mutations:
        changed = copy.deepcopy(material)
        mutate(changed)
        assert proposal_fingerprint(changed) != expected


def test_confirmed_success_runs_in_date_order_and_strips_private_ids() -> None:
    scheduling, calls, _ = service()
    reviewed = preview(scheduling)
    calls.clear()

    result = scheduling.schedule(
        reviewed["approval_token"], reviewed["proposal_fingerprint"], confirmed=True
    )

    assert [item[0] for item in calls] == ["calendar", "write", "write"]
    assert [item[2] for item in calls if item[0] == "write"] == [
        "2030-04-02",
        "2030-04-04",
    ]
    assert result["requested_session_count"] == 2
    assert result["completed_session_count"] == 2
    assert result["partial_failure"] is False
    assert result["uncertain"] is False
    assert all(item["safe_status"] == "scheduled" for item in result["sessions"])
    serialized = repr(result).casefold()
    assert "private-workout-id" not in serialized
    assert "private-schedule-id" not in serialized
    assert "workout_id" not in serialized
    assert "scheduled_workout_id" not in serialized


def test_approval_is_one_use_even_after_success() -> None:
    scheduling, _, _ = service()
    reviewed = preview(scheduling)
    scheduling.schedule(
        reviewed["approval_token"], reviewed["proposal_fingerprint"], confirmed=True
    )
    with pytest.raises(ExpiredWeeklyPlanApprovalError, match="already used"):
        scheduling.schedule(
            reviewed["approval_token"],
            reviewed["proposal_fingerprint"],
            confirmed=True,
        )


def test_wrong_fingerprint_does_not_authorize_or_consume_approval() -> None:
    scheduling, calls, _ = service()
    reviewed = preview(scheduling)
    calls.clear()
    with pytest.raises(InvalidWeeklyPlanApprovalError, match="does not match"):
        scheduling.schedule(
            reviewed["approval_token"], "sha256:" + "0" * 64, confirmed=True
        )
    assert calls == []
    scheduling.schedule(
        reviewed["approval_token"], reviewed["proposal_fingerprint"], confirmed=False
    )


def test_expired_approval_is_rejected_offline() -> None:
    now = [0.0]
    store = ApprovalStore(now=lambda: now[0], token_factory=lambda: "B" * 43)
    source = proposal()
    calls: list[Any] = []
    scheduling = WeeklyPlanSchedulingService(
        lambda: Planner(source, [], calls),  # type: ignore[arg-type]
        lambda: Reader({"calendar": []}, calls),
        lambda: Writer([success(), success()], calls),
        store,
    )
    reviewed = preview(scheduling)
    calls.clear()
    now[0] = 901.0

    with pytest.raises(ExpiredWeeklyPlanApprovalError, match="expired"):
        scheduling.schedule(
            reviewed["approval_token"], reviewed["proposal_fingerprint"], confirmed=True
        )
    assert calls == []


def test_all_definitions_and_aggregates_revalidate_before_calendar_or_writes() -> None:
    source = proposal()
    source["proposed_sessions"][1]["aggregates"]["known_distance_m"] = 1
    intended = WeeklyPlanSchedulingService._intended_writes(source)
    fingerprint = proposal_fingerprint(
        {"proposal": source, "intended_garmin_writes": intended}
    )
    store = ApprovalStore(token_factory=lambda: "C" * 43)
    token = store.put(fingerprint, source, ())
    calls: list[Any] = []
    scheduling = WeeklyPlanSchedulingService(
        lambda: Planner(source, [], calls),  # type: ignore[arg-type]
        lambda: Reader({"calendar": []}, calls),
        lambda: Writer([success(), success()], calls),
        store,
    )

    with pytest.raises(MalformedWeeklyPlanError, match="revalidation"):
        scheduling.schedule(token, fingerprint, confirmed=True)
    assert calls == []


def test_changed_calendar_stops_before_writer_construction() -> None:
    existing = [scheduled()]
    scheduling, calls, _ = service(
        preview_calendar=existing,
        fresh_calendar=[scheduled(schedule_id="8002")],
    )
    reviewed = preview(scheduling)
    calls.clear()

    with pytest.raises(StaleWeeklyPlanError):
        scheduling.schedule(
            reviewed["approval_token"], reviewed["proposal_fingerprint"], confirmed=True
        )
    assert [item[0] for item in calls] == ["calendar"]


def test_new_commitment_on_approved_date_is_a_conflict_before_writes() -> None:
    scheduling, calls, _ = service(fresh_calendar=[scheduled("2030-04-02")])
    reviewed = preview(scheduling)
    calls.clear()

    with pytest.raises(WeeklyPlanConflictError):
        scheduling.schedule(
            reviewed["approval_token"], reviewed["proposal_fingerprint"], confirmed=True
        )
    assert [item[0] for item in calls] == ["calendar"]


@pytest.mark.parametrize(
    "error",
    [
        WorkoutAuthenticationError("secret authentication detail"),
        WorkoutEndpointError("Garmin scheduled workouts endpoint failed"),
        WorkoutEndpointError("Garmin scheduled workouts endpoint rate limit reached"),
        WorkoutUnsupportedError("unsupported"),
        WorkoutResponseError("malformed"),
    ],
)
def test_prewrite_calendar_errors_never_construct_writer(error: Exception) -> None:
    scheduling, calls, state = service()
    reviewed = preview(scheduling)
    calls.clear()
    state["error"] = error

    with pytest.raises(type(error)):
        scheduling.schedule(
            reviewed["approval_token"], reviewed["proposal_fingerprint"], confirmed=True
        )
    assert calls == [("calendar", "2030-04-01", "2030-04-07")]


@pytest.mark.parametrize(
    ("error", "uncertain", "reason"),
    [
        (WorkoutAuthenticationError("private"), False, "authentication_failed"),
        (WorkoutEndpointError("endpoint failed"), False, "endpoint_failed"),
        (WorkoutUnsupportedError("private"), False, "unsupported_client"),
        (
            WorkoutResponseError("private raw response"),
            True,
            "malformed_or_uncertain_creation_response",
        ),
        (
            WorkoutUncertainResultError("private upstream exception"),
            True,
            "uncertain_creation_result",
        ),
    ],
)
def test_first_creation_failure_is_compact_and_stops(
    error: Exception, uncertain: bool, reason: str
) -> None:
    scheduling, calls, _ = service(outcomes=[error])
    reviewed = preview(scheduling)
    calls.clear()

    result = scheduling.schedule(
        reviewed["approval_token"], reviewed["proposal_fingerprint"], confirmed=True
    )

    assert [item[0] for item in calls] == ["calendar", "write"]
    assert result["completed_session_count"] == 0
    assert result["partial_failure"] is True
    assert result["uncertain"] is uncertain
    assert result["sessions"][0]["failure_reason"] == reason
    assert result["sessions"][1]["safe_status"] == "not_attempted"
    assert "private" not in repr(result).casefold()


@pytest.mark.parametrize(
    ("message", "uncertain"),
    [
        ("Creation succeeded, but scheduling failed.", False),
        ("Creation succeeded, but scheduling is uncertain.", True),
    ],
)
def test_created_unscheduled_stops_and_preserves_partial_state(
    message: str, uncertain: bool
) -> None:
    partial = {
        "created": True,
        "scheduled": False,
        "workout_id": "private-id",
        "scheduled_workout_id": None,
        "partial_failure": True,
        "message": message,
    }
    scheduling, calls, _ = service(outcomes=[partial])
    reviewed = preview(scheduling)
    calls.clear()

    result = scheduling.schedule(
        reviewed["approval_token"], reviewed["proposal_fingerprint"], confirmed=True
    )

    assert [item[0] for item in calls] == ["calendar", "write"]
    assert result["sessions"][0]["safe_status"] == (
        "uncertain" if uncertain else "created_unscheduled"
    )
    assert result["sessions"][0]["created"] is True
    assert result["sessions"][1]["safe_status"] == "not_attempted"
    assert "private-id" not in repr(result)


def test_successful_early_session_then_failure_marks_later_not_attempted() -> None:
    scheduling, calls, _ = service(
        plan=proposal(3),
        outcomes=[success(), WorkoutEndpointError("failed")],
    )
    reviewed = scheduling.preview(
        "2030-04-01",
        {
            "plan_start_date": "2030-03-04",
            "desired_sessions": 3,
            "maximum_sessions": 3,
        },
    )
    calls.clear()

    result = scheduling.schedule(
        reviewed["approval_token"], reviewed["proposal_fingerprint"], confirmed=True
    )

    assert [item["safe_status"] for item in result["sessions"]] == [
        "scheduled",
        "failed_not_created",
        "not_attempted",
    ]
    assert result["completed_session_count"] == 1
    assert result["remaining_sessions_not_attempted"] == 1
    assert len([item for item in calls if item[0] == "write"]) == 2
