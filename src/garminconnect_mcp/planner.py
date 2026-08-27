from __future__ import annotations

import math
import re
import unicodedata
from collections.abc import Callable
from datetime import date, timedelta
from statistics import median
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .activities import NormalizedActivity
from .heart_rate_zones import NormalizedHeartRateZones
from .recovery import NormalizedHRV
from .training import summarize_running_weeks
from .workout_builder import WorkoutDefinition, aggregate_workout
from .workouts import NormalizedScheduledWorkout, workout_is_running

ACTIVITY_LOOKBACK_DAYS = 28
RECOVERY_LOOKBACK_DAYS = 7
MAX_USER_NOTE_LENGTH = 200
_DATE_PATTERN = re.compile(r"\d{4}-\d{2}-\d{2}")
_NOTE_PATTERN = re.compile(r"[\x20-\x7e]+")


class ProposalError(RuntimeError):
    """Base class for stable, secret-safe weekly-proposal failures."""


class InvalidProposalRequestError(ProposalError, ValueError):
    pass


class MalformedProposalDataError(ProposalError):
    pass


class ProposalConstraints(BaseModel):
    """Small strict public constraint model for one proposal week."""

    model_config = ConfigDict(extra="forbid", strict=True)

    available_dates: list[str] | None = Field(default=None, min_length=1, max_length=7)
    maximum_sessions: int = Field(default=3, strict=True, ge=1, le=7)
    desired_sessions: int | None = Field(default=None, strict=True, ge=1, le=7)
    preferred_long_run_date: str | None = None
    maximum_weekly_distance_m: float | None = Field(
        default=None, strict=True, ge=1000, le=300_000, allow_inf_nan=False
    )
    user_note: str | None = Field(
        default=None, strict=True, min_length=1, max_length=MAX_USER_NOTE_LENGTH
    )

    @model_validator(mode="after")
    def validate_values(self) -> ProposalConstraints:
        dates = self.available_dates or []
        if len(set(dates)) != len(dates):
            raise ValueError("available_dates must not contain duplicates")
        for value in [*dates, self.preferred_long_run_date]:
            if value is not None:
                _strict_date(value, name="constraint date")
        if self.preferred_long_run_date is not None and (
            self.available_dates is not None
            and self.preferred_long_run_date not in self.available_dates
        ):
            raise ValueError("preferred_long_run_date must be an available date")
        if (
            self.desired_sessions is not None
            and self.desired_sessions > self.maximum_sessions
        ):
            raise ValueError("desired_sessions must not exceed maximum_sessions")
        if self.user_note is not None:
            if self.user_note != self.user_note.strip():
                raise ValueError("user_note must not have surrounding whitespace")
            if _NOTE_PATTERN.fullmatch(self.user_note) is None:
                raise ValueError(
                    "user_note must contain printable ASCII characters only"
                )
            if any(
                unicodedata.category(character).startswith("C")
                for character in self.user_note
            ):
                raise ValueError("user_note must not contain control characters")
        return self


class ActivityReader(Protocol):
    def running_activities_by_date(
        self, start_date: str, end_date: str
    ) -> list[NormalizedActivity]: ...


class RecoveryReader(Protocol):
    def hrv_range(self, start_date: str, end_date: str) -> list[NormalizedHRV]: ...


class ScheduleReader(Protocol):
    def scheduled_workouts(
        self, start_date: str, end_date: str
    ) -> list[NormalizedScheduledWorkout]: ...


class HeartRateZoneReader(Protocol):
    def running_zones(self) -> NormalizedHeartRateZones: ...


def _strict_date(value: Any, *, name: str) -> date:
    if not isinstance(value, str) or _DATE_PATTERN.fullmatch(value) is None:
        raise InvalidProposalRequestError(f"{name} must use strict YYYY-MM-DD format")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise InvalidProposalRequestError(
            f"{name} must use strict YYYY-MM-DD format"
        ) from exc
    if parsed.isoformat() != value:
        raise InvalidProposalRequestError(f"{name} must use strict YYYY-MM-DD format")
    return parsed


def validate_proposal_request(
    week_start: Any, constraints: ProposalConstraints | dict[str, Any]
) -> tuple[date, ProposalConstraints]:
    """Validate the complete public request without accessing any provider."""
    monday = _strict_date(week_start, name="week_start")
    if monday.weekday() != 0:
        raise InvalidProposalRequestError("week_start must be a Monday")
    try:
        monday - timedelta(days=ACTIVITY_LOOKBACK_DAYS)
        monday + timedelta(days=6)
    except OverflowError as exc:
        raise InvalidProposalRequestError(
            "week_start cannot support the bounded proposal ranges"
        ) from exc
    try:
        normalized = (
            constraints
            if isinstance(constraints, ProposalConstraints)
            else ProposalConstraints.model_validate(constraints, strict=True)
        )
    except (TypeError, ValueError) as exc:
        raise InvalidProposalRequestError("constraints are invalid") from exc
    week_dates = {(monday + timedelta(days=offset)).isoformat() for offset in range(7)}
    constrained_dates = normalized.available_dates or sorted(week_dates)
    if any(value not in week_dates for value in constrained_dates):
        raise InvalidProposalRequestError(
            "available_dates must fall within the requested week"
        )
    if (
        normalized.preferred_long_run_date is not None
        and normalized.preferred_long_run_date not in week_dates
    ):
        raise InvalidProposalRequestError(
            "preferred_long_run_date must fall within the requested week"
        )
    return monday, normalized


def _distance_workout(
    name: str,
    total_distance_m: float,
    heart_rate_target: tuple[int, int],
) -> WorkoutDefinition:
    warmup = round(total_distance_m * 0.1 / 100) * 100
    cooldown = warmup
    main = total_distance_m - warmup - cooldown
    return WorkoutDefinition.model_validate(
        {
            "sport_type": "running",
            "name": name,
            "description": "Proposal only; main step uses configured running Zone 2.",
            "steps": [
                {
                    "step_type": "warmup",
                    "duration": {"duration_type": "distance", "distance_m": warmup},
                    "target": {"target_type": "none"},
                },
                {
                    "step_type": "run",
                    "duration": {"duration_type": "distance", "distance_m": main},
                    "target": {
                        "target_type": "heart_rate_range",
                        "minimum_heart_rate_bpm": heart_rate_target[0],
                        "maximum_heart_rate_bpm": heart_rate_target[1],
                    },
                },
                {
                    "step_type": "cooldown",
                    "duration": {
                        "duration_type": "distance",
                        "distance_m": cooldown,
                    },
                    "target": {"target_type": "none"},
                },
            ],
        },
        strict=True,
    )


def _compact_commitment(item: NormalizedScheduledWorkout) -> dict[str, Any]:
    return {
        "date": item["scheduled_date"],
        "name": item["name"],
        "sport_type": item["sport_type"],
        "estimated_duration_s": item["estimated_duration_s"],
        "estimated_distance_m": item["estimated_distance_m"],
        "preserved": True,
    }


class WeeklyProposalService:
    """Read normalized facts and produce a deterministic proposal without writes."""

    def __init__(
        self,
        activity_reader: Callable[[], ActivityReader],
        recovery_reader: Callable[[], RecoveryReader],
        schedule_reader: Callable[[], ScheduleReader],
        heart_rate_zone_reader: Callable[[], HeartRateZoneReader],
    ) -> None:
        self._activity_reader = activity_reader
        self._recovery_reader = recovery_reader
        self._schedule_reader = schedule_reader
        self._heart_rate_zone_reader = heart_rate_zone_reader

    def propose(
        self, week_start: Any, constraints: ProposalConstraints | dict[str, Any]
    ) -> dict[str, Any]:
        monday, constraints = validate_proposal_request(week_start, constraints)
        week_end = monday + timedelta(days=6)
        lookback_end = monday - timedelta(days=1)
        lookback_start = monday - timedelta(days=ACTIVITY_LOOKBACK_DAYS)
        recovery_start = monday - timedelta(days=RECOVERY_LOOKBACK_DAYS)

        activities = self._activity_reader().running_activities_by_date(
            lookback_start.isoformat(), lookback_end.isoformat()
        )
        recovery = self._recovery_reader().hrv_range(
            recovery_start.isoformat(), lookback_end.isoformat()
        )
        scheduled = self._schedule_reader().scheduled_workouts(
            monday.isoformat(), week_end.isoformat()
        )
        heart_rate_zones = self._heart_rate_zone_reader().running_zones()
        try:
            return self._build(
                monday,
                constraints,
                activities,
                recovery,
                scheduled,
                heart_rate_zones,
            )
        except (KeyError, TypeError, ValueError, ArithmeticError) as exc:
            raise MalformedProposalDataError(
                "Normalized proposal input was malformed"
            ) from exc

    def _build(
        self,
        monday: date,
        constraints: ProposalConstraints,
        activities: list[NormalizedActivity],
        recovery: list[NormalizedHRV],
        scheduled: list[NormalizedScheduledWorkout],
        heart_rate_zones: NormalizedHeartRateZones,
    ) -> dict[str, Any]:
        week_end = monday + timedelta(days=6)
        lookback_start = monday - timedelta(days=ACTIVITY_LOOKBACK_DAYS)
        lookback_end = monday - timedelta(days=1)
        weekly = summarize_running_weeks(
            activities, lookback_start.isoformat(), lookback_end.isoformat()
        )
        weeks = weekly["weeks"]
        qualifying = [
            week
            for week in weeks
            if week["activity_count"] > 0
            and week["distance_coverage"]["complete"]
            and week["distance_m"] is not None
        ]
        history_sufficient = len(qualifying) >= 2
        complete_distances = [float(week["distance_m"]) for week in qualifying]
        complete_frequencies = [week["activity_count"] for week in qualifying]
        baseline_distance = (
            round(median(complete_distances) / 100) * 100
            if history_sufficient
            else None
        )
        baseline_sessions = (
            max(1, math.floor(median(complete_frequencies)))
            if history_sufficient
            else None
        )

        running_commitments = [item for item in scheduled if workout_is_running(item)]
        compact_commitments = [
            _compact_commitment(item) for item in running_commitments
        ]
        occupied_dates = {
            item["scheduled_date"]
            for item in running_commitments
            if item["scheduled_date"] is not None
        }
        available_dates = sorted(
            constraints.available_dates
            or [(monday + timedelta(days=offset)).isoformat() for offset in range(7)]
        )
        free_dates = [value for value in available_dates if value not in occupied_dates]

        statuses = [item["status"] for item in recovery if item["status"] is not None]
        zone2 = next(
            (zone for zone in heart_rate_zones["zones"] if zone["zone"] == 2), None
        )
        if zone2 is None:
            raise ValueError("normalized running Zone 2 was unavailable")
        zone2_target = (
            zone2["minimum_heart_rate_bpm"],
            zone2["maximum_heart_rate_bpm"],
        )
        low_statuses = [
            status
            for status in statuses
            if status.casefold() in {"low", "unbalanced", "poor"}
        ]
        recovery_adjustment = 0.9 if len(low_statuses) >= 2 else 1.0
        warnings: list[str] = []
        unavailable: list[str] = [
            "Hard-session classification is unavailable from normalized inputs"
        ]
        if not history_sufficient:
            warnings.append(
                "Insufficient history: at least two non-empty weeks with complete "
                "distance coverage are required for new sessions."
            )
        if len(recovery) < RECOVERY_LOOKBACK_DAYS:
            unavailable.append(
                "HRV records were unavailable for one or more lookback days"
            )
        if not statuses:
            unavailable.append("HRV status was unavailable")
        if low_statuses:
            warnings.append(
                "Garmin reported low, unbalanced, or poor HRV status on "
                f"{len(low_statuses)} lookback day(s); this is not a medical "
                "conclusion."
            )
        if len(running_commitments) > constraints.maximum_sessions:
            warnings.append(
                "Existing running commitments exceed maximum_sessions; they are "
                "preserved and no new session is proposed."
            )

        proposed: list[dict[str, Any]] = []
        target_distance = None
        session_limit = 0
        if history_sufficient and baseline_distance is not None and baseline_sessions:
            target_distance = baseline_distance * recovery_adjustment
            if constraints.maximum_weekly_distance_m is not None:
                target_distance = min(
                    target_distance, constraints.maximum_weekly_distance_m
                )
            target_distance = max(0.0, round(target_distance / 100) * 100)
            session_limit = min(
                constraints.desired_sessions or baseline_sessions,
                constraints.maximum_sessions - len(running_commitments),
                len(free_dates),
                int(target_distance // 300),
            )
            session_limit = max(0, session_limit)
            if (
                constraints.desired_sessions is not None
                and session_limit < constraints.desired_sessions
            ):
                warnings.append(
                    "desired_sessions could not be fully met after safety, "
                    "commitment, available-date, and minimum-distance limits."
                )

        selected_dates = free_dates[:session_limit]
        if session_limit > 0 and constraints.preferred_long_run_date in free_dates:
            long_date = constraints.preferred_long_run_date
            if long_date not in selected_dates:
                selected_dates[-1] = long_date
                selected_dates.sort()
        else:
            long_date = selected_dates[-1] if selected_dates else None

        if target_distance is not None and selected_dates:
            long_run_share = 1.0 if len(selected_dates) == 1 else 0.6
            if len(selected_dates) >= 3:
                long_run_share = 0.4
            long_distance = round((target_distance * long_run_share) / 100) * 100
            easy_total = target_distance - long_distance
            easy_count = len(selected_dates) - 1
            easy_distance = (
                round((easy_total / easy_count) / 100) * 100 if easy_count else 0.0
            )
            distances = {value: easy_distance for value in selected_dates}
            assert long_date is not None
            distances[long_date] = target_distance - easy_distance * easy_count
            for execution_order, proposed_date in enumerate(selected_dates, start=1):
                purpose = "long_run" if proposed_date == long_date else "easy_run"
                definition = _distance_workout(
                    "Proposed Long Run"
                    if purpose == "long_run"
                    else "Proposed Easy Run",
                    distances[proposed_date],
                    zone2_target,
                )
                proposed.append(
                    {
                        "date": proposed_date,
                        "purpose": purpose,
                        "definition": definition.model_dump(mode="json"),
                        "execution_order": execution_order,
                        "aggregates": aggregate_workout(definition),
                    }
                )

        proposed_distance = math.fsum(
            item["aggregates"]["known_distance_m"] for item in proposed
        )
        commitment_distance_values = [
            item["estimated_distance_m"]
            for item in compact_commitments
            if item["estimated_distance_m"] is not None
        ]
        weekly_distance_complete = len(commitment_distance_values) == len(
            compact_commitments
        )
        known_weekly_distance = proposed_distance + math.fsum(
            commitment_distance_values
        )
        commitment_duration_values = [
            item["estimated_duration_s"]
            for item in compact_commitments
            if item["estimated_duration_s"] is not None
        ]
        weekly_duration_complete = not proposed and len(
            commitment_duration_values
        ) == len(compact_commitments)
        known_weekly_duration = math.fsum(commitment_duration_values)

        return {
            "week_start": monday.isoformat(),
            "week_end": week_end.isoformat(),
            "lookback_start": lookback_start.isoformat(),
            "lookback_end": lookback_end.isoformat(),
            "factual_training_summary": {
                "activity_count": weekly["assigned_activity_count"],
                "weekly_distance_m": [week["distance_m"] for week in weeks],
                "weekly_duration_s": [week["duration_s"] for week in weeks],
                "weekly_activity_count": [week["activity_count"] for week in weeks],
                "weekly_longest_run_distance_m": [
                    week["longest_run"]["distance_m"]
                    if week["longest_run"] is not None
                    else None
                    for week in weeks
                ],
                "distance_complete_week_count": len(qualifying),
                "history_sufficient": history_sufficient,
                "baseline_weekly_distance_m": baseline_distance,
                "baseline_sessions": baseline_sessions,
            },
            "training_measurement_coverage": {
                "lookback_day_count": ACTIVITY_LOOKBACK_DAYS,
                "week_count": len(weeks),
                "unassigned_activity_count": weekly["unassigned_activity_count"],
                "distance_by_week": [week["distance_coverage"] for week in weeks],
                "duration_by_week": [week["duration_coverage"] for week in weeks],
            },
            "factual_recovery_summary": {
                "range_start": (
                    monday - timedelta(days=RECOVERY_LOOKBACK_DAYS)
                ).isoformat(),
                "range_end": lookback_end.isoformat(),
                "record_count": len(recovery),
                "status_available_count": len(statuses),
                "low_unbalanced_or_poor_status_count": len(low_statuses),
            },
            "recovery_measurement_coverage": {
                "expected_day_count": RECOVERY_LOOKBACK_DAYS,
                "record_count": len(recovery),
                "complete": len(recovery) == RECOVERY_LOOKBACK_DAYS,
            },
            "factual_heart_rate_zone_summary": {
                "sport": heart_rate_zones["sport"],
                "source_sport": heart_rate_zones["source_sport"],
                "training_method": heart_rate_zones["training_method"],
                "zone2_minimum_heart_rate_bpm": zone2_target[0],
                "zone2_maximum_heart_rate_bpm": zone2_target[1],
            },
            "heart_rate_zone_measurement_coverage": {
                "running_or_default_profile_available": True,
                "zone2_complete": True,
            },
            "constraints": {
                "available_dates": available_dates,
                "maximum_sessions": constraints.maximum_sessions,
                "desired_sessions": constraints.desired_sessions,
                "preferred_long_run_date": constraints.preferred_long_run_date,
                "maximum_weekly_distance_m": constraints.maximum_weekly_distance_m,
                "user_note": constraints.user_note,
            },
            "existing_scheduled_commitments": compact_commitments,
            "rules_applied": [
                "Baseline requires at least two non-empty lookback weeks with "
                "complete distance coverage.",
                "Baseline distance is the median qualifying weekly distance, "
                "rounded to 100 m.",
                "Baseline sessions is the floor of the median qualifying weekly "
                "run count.",
                "Two or more low, unbalanced, or poor HRV statuses multiply new "
                "distance by 0.90.",
                "The optional distance cap is applied after the recovery adjustment.",
                "Existing running commitments consume session capacity and "
                "occupied dates.",
                "desired_sessions sets the requested count; maximum_sessions "
                "remains a hard safety cap.",
                "The long run receives 100% with one new session, 60% with two, "
                "or 40% with three or more; remaining distance is divided equally.",
                "Every session uses 10% warmup, 80% configured Zone 2 run, and "
                "10% cooldown distance.",
            ],
            "rule_calculations": {
                "baseline_weekly_distance_m": baseline_distance,
                "recovery_multiplier": recovery_adjustment,
                "distance_cap_m": constraints.maximum_weekly_distance_m,
                "new_session_limit": session_limit,
                "new_distance_target_m": target_distance,
                "long_run_share": (
                    None
                    if not selected_dates
                    else (1.0 if len(selected_dates) == 1 else 0.6)
                    if len(selected_dates) < 3
                    else 0.4
                ),
            },
            "warnings": warnings,
            "unavailable_inputs": unavailable,
            "proposed_sessions": proposed,
            "proposed_weekly_aggregates": {
                "existing_running_commitment_count": len(compact_commitments),
                "new_session_count": len(proposed),
                "total_session_count": len(compact_commitments) + len(proposed),
                "known_distance_m": known_weekly_distance,
                "total_distance_m": (
                    known_weekly_distance if weekly_distance_complete else None
                ),
                "distance_total_complete": weekly_distance_complete,
                "known_duration_s": known_weekly_duration,
                "total_duration_s": (
                    known_weekly_duration if weekly_duration_complete else None
                ),
                "duration_total_complete": weekly_duration_complete,
            },
            "proposal_only": True,
            "created": False,
            "scheduled": False,
            "message": "Proposal only: no Garmin workout or calendar change occurred.",
        }
