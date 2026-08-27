from __future__ import annotations

import copy
import hashlib
import hmac
import json
import re
import secrets
import time
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass
from threading import RLock
from typing import Any, Protocol

from .planner import (
    ProposalConstraints,
    WeeklyProposalService,
    validate_proposal_request,
)
from .provider import (
    WorkoutAuthenticationError,
    WorkoutEndpointError,
    WorkoutProviderError,
    WorkoutResponseError,
    WorkoutUncertainResultError,
    WorkoutUnsupportedError,
    validate_workout_date,
)
from .workout_builder import WorkoutDefinition, aggregate_workout
from .workouts import NormalizedScheduledWorkout

APPROVAL_TTL_S = 15 * 60
MAX_PENDING_APPROVALS = 32
_TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_-]{32,128}")
_FINGERPRINT_PATTERN = re.compile(r"sha256:[0-9a-f]{64}")


class WeeklyPlanError(RuntimeError):
    """Base class for stable, secret-safe weekly scheduling failures."""


class InvalidWeeklyPlanApprovalError(WeeklyPlanError, ValueError):
    pass


class ExpiredWeeklyPlanApprovalError(WeeklyPlanError):
    pass


class StaleWeeklyPlanError(WeeklyPlanError):
    pass


class WeeklyPlanConflictError(WeeklyPlanError):
    pass


class MalformedWeeklyPlanError(WeeklyPlanError):
    pass


class ScheduleReader(Protocol):
    def scheduled_workouts(
        self, start_date: str, end_date: str
    ) -> list[NormalizedScheduledWorkout]: ...


class WorkoutWriter(Protocol):
    def create_and_schedule_running_workout(
        self, definition: WorkoutDefinition, scheduled_date: str
    ) -> dict[str, Any]: ...


@dataclass(frozen=True)
class _Approval:
    fingerprint: str
    proposal: dict[str, Any]
    calendar_snapshot: tuple[dict[str, Any], ...]
    expires_at: float


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=True,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("ascii")


def proposal_fingerprint(proposal: dict[str, Any]) -> str:
    """Hash every reviewed fact, constraint, definition, target, and aggregate."""
    return f"sha256:{hashlib.sha256(_canonical_json(proposal)).hexdigest()}"


def _calendar_snapshot(
    scheduled: list[NormalizedScheduledWorkout],
) -> tuple[dict[str, Any], ...]:
    compact = [
        {
            "scheduled_workout_id": item["scheduled_workout_id"],
            "date": item["scheduled_date"],
            "workout_id": item["workout_id"],
            "name": item["name"],
            "sport_type": item["sport_type"],
            "estimated_duration_s": item["estimated_duration_s"],
            "estimated_distance_m": item["estimated_distance_m"],
        }
        for item in scheduled
    ]
    compact.sort(
        key=lambda item: (
            item["date"] or "",
            item["scheduled_workout_id"] or "",
            item["workout_id"] or "",
            item["sport_type"] or "",
            item["name"] or "",
            item["estimated_duration_s"] or -1,
            item["estimated_distance_m"] or -1,
        )
    )
    return tuple(compact)


class ApprovalStore:
    """Small process-local, bounded, expiring, one-use approval store."""

    def __init__(
        self,
        *,
        now: Callable[[], float] = time.monotonic,
        token_factory: Callable[[], str] = lambda: secrets.token_urlsafe(32),
    ) -> None:
        self._now = now
        self._token_factory = token_factory
        self._items: OrderedDict[str, _Approval] = OrderedDict()
        self._lock = RLock()

    def put(
        self,
        fingerprint: str,
        proposal: dict[str, Any],
        calendar_snapshot: tuple[dict[str, Any], ...],
    ) -> str:
        with self._lock:
            self._prune()
            token = self._token_factory()
            if _TOKEN_PATTERN.fullmatch(token) is None or token in self._items:
                raise RuntimeError("Approval token generation failed")
            self._items[token] = _Approval(
                fingerprint=fingerprint,
                proposal=copy.deepcopy(proposal),
                calendar_snapshot=copy.deepcopy(calendar_snapshot),
                expires_at=self._now() + APPROVAL_TTL_S,
            )
            while len(self._items) > MAX_PENDING_APPROVALS:
                self._items.popitem(last=False)
            return token

    def peek(self, token: str, fingerprint: str) -> _Approval:
        return self._get(token, fingerprint, consume=False)

    def take(self, token: str, fingerprint: str) -> _Approval:
        return self._get(token, fingerprint, consume=True)

    def _get(self, token: str, fingerprint: str, *, consume: bool) -> _Approval:
        _validate_approval_values(token, fingerprint)
        with self._lock:
            approval = self._items.get(token)
            if approval is None:
                raise ExpiredWeeklyPlanApprovalError(
                    "Weekly-plan approval is unknown, expired, or already used; "
                    "generate a new preview"
                )
            if approval.expires_at <= self._now():
                del self._items[token]
                raise ExpiredWeeklyPlanApprovalError(
                    "Weekly-plan approval expired; generate a new preview"
                )
            if not hmac.compare_digest(approval.fingerprint, fingerprint):
                raise InvalidWeeklyPlanApprovalError(
                    "Proposal fingerprint does not match the reviewed preview"
                )
            if consume:
                del self._items[token]
            return copy.deepcopy(approval)

    def _prune(self) -> None:
        now = self._now()
        expired = [
            token for token, item in self._items.items() if item.expires_at <= now
        ]
        for token in expired:
            del self._items[token]


def _validate_approval_values(token: Any, fingerprint: Any) -> None:
    if not isinstance(token, str) or _TOKEN_PATTERN.fullmatch(token) is None:
        raise InvalidWeeklyPlanApprovalError("approval_token is invalid")
    if (
        not isinstance(fingerprint, str)
        or _FINGERPRINT_PATTERN.fullmatch(fingerprint) is None
    ):
        raise InvalidWeeklyPlanApprovalError("proposal_fingerprint is invalid")


class WeeklyPlanSchedulingService:
    """Preview and execute exactly one approval-bound weekly proposal."""

    def __init__(
        self,
        proposal_service: Callable[[], WeeklyProposalService],
        schedule_reader: Callable[[], ScheduleReader],
        workout_writer: Callable[[], WorkoutWriter],
        approval_store: ApprovalStore,
    ) -> None:
        self._proposal_service = proposal_service
        self._schedule_reader = schedule_reader
        self._workout_writer = workout_writer
        self._approval_store = approval_store

    def preview(
        self, week_start: Any, constraints: ProposalConstraints | dict[str, Any]
    ) -> dict[str, Any]:
        monday, normalized = validate_proposal_request(week_start, constraints)
        proposal, scheduled = self._proposal_service().propose_with_calendar_snapshot(
            monday.isoformat(), normalized
        )
        intended_writes = self._intended_writes(proposal)
        approval_material = {
            "proposal": proposal,
            "intended_garmin_writes": intended_writes,
        }
        fingerprint = proposal_fingerprint(approval_material)
        token = self._approval_store.put(
            fingerprint, proposal, _calendar_snapshot(scheduled)
        )
        return {
            **proposal,
            "intended_garmin_writes": intended_writes,
            "intended_creation_count": len(intended_writes),
            "intended_schedule_count": len(intended_writes),
            "proposal_fingerprint": fingerprint,
            "approval_token": token,
            "approval_expires_in_s": APPROVAL_TTL_S,
            "preview_only": True,
            "proposal_only": True,
            "created": False,
            "scheduled": False,
            "message": "Preview only: no Garmin workout or calendar change occurred.",
        }

    def schedule(
        self,
        approval_token: Any,
        fingerprint: Any,
        *,
        confirmed: Any = False,
    ) -> dict[str, Any]:
        _validate_approval_values(approval_token, fingerprint)
        if not isinstance(confirmed, bool):
            raise InvalidWeeklyPlanApprovalError("confirmed must be a boolean")
        approval = (
            self._approval_store.take(approval_token, fingerprint)
            if confirmed
            else self._approval_store.peek(approval_token, fingerprint)
        )
        try:
            approval_material = {
                "proposal": approval.proposal,
                "intended_garmin_writes": self._intended_writes(approval.proposal),
            }
            recalculated_fingerprint = proposal_fingerprint(approval_material)
        except (KeyError, TypeError, ValueError) as exc:
            raise MalformedWeeklyPlanError(
                "Approved weekly proposal failed fingerprint revalidation"
            ) from exc
        if not hmac.compare_digest(recalculated_fingerprint, approval.fingerprint):
            raise MalformedWeeklyPlanError(
                "Approved weekly proposal failed fingerprint revalidation"
            )
        sessions = self._validated_sessions(approval.proposal)
        if not confirmed:
            return self._unconfirmed_result(approval, sessions)

        week_start = approval.proposal["week_start"]
        week_end = approval.proposal["week_end"]
        fresh_calendar = self._schedule_reader().scheduled_workouts(
            week_start, week_end
        )
        fresh_snapshot = _calendar_snapshot(fresh_calendar)
        if fresh_snapshot != approval.calendar_snapshot:
            proposed_dates = {item["date"] for item in sessions}
            previous_dates = {item["date"] for item in approval.calendar_snapshot}
            new_dates = {item["date"] for item in fresh_snapshot} - previous_dates
            if proposed_dates & new_dates:
                raise WeeklyPlanConflictError(
                    "The Garmin calendar now conflicts with an approved session; "
                    "generate and approve a new preview"
                )
            raise StaleWeeklyPlanError(
                "The Garmin calendar changed after preview; generate and approve "
                "a new preview"
            )

        results: list[dict[str, Any]] = []
        completed = 0
        partial_failure = False
        uncertain = False
        writer = self._workout_writer() if sessions else None
        for index, session in enumerate(sessions):
            assert writer is not None
            try:
                outcome = writer.create_and_schedule_running_workout(
                    session["definition"], session["date"]
                )
            except WorkoutProviderError as exc:
                partial_failure = True
                uncertain = isinstance(
                    exc, (WorkoutUncertainResultError, WorkoutResponseError)
                )
                results.append(self._failed_session(session, exc, uncertain))
                results.extend(
                    self._not_attempted(item) for item in sessions[index + 1 :]
                )
                break

            compact = self._compact_outcome(session, outcome)
            results.append(compact)
            if compact["safe_status"] == "scheduled":
                completed += 1
                continue
            partial_failure = True
            uncertain = compact["uncertain"]
            results.extend(self._not_attempted(item) for item in sessions[index + 1 :])
            break

        remaining = sum(item["safe_status"] == "not_attempted" for item in results)
        return {
            "week_start": week_start,
            "week_end": week_end,
            "proposal_fingerprint": fingerprint,
            "requested_session_count": len(sessions),
            "completed_session_count": completed,
            "sessions": results,
            "partial_failure": partial_failure,
            "uncertain": uncertain,
            "remaining_sessions_not_attempted": remaining,
            "next_action": self._next_action(partial_failure, uncertain),
        }

    @staticmethod
    def _intended_writes(proposal: dict[str, Any]) -> list[dict[str, Any]]:
        return [
            {
                "execution_order": item["execution_order"],
                "date": item["date"],
                "purpose": item["purpose"],
                "name": item["definition"]["name"],
                "definition": item["definition"],
                "aggregates": item["aggregates"],
                "action": (
                    "Create one new workout, then schedule only its returned ID "
                    "on this exact date."
                ),
            }
            for item in proposal["proposed_sessions"]
        ]

    @staticmethod
    def _validated_sessions(proposal: dict[str, Any]) -> list[dict[str, Any]]:
        try:
            week_start = validate_workout_date(
                proposal["week_start"], name="week_start"
            )
            week_end = validate_workout_date(proposal["week_end"], name="week_end")
            raw_sessions = proposal["proposed_sessions"]
            sessions: list[dict[str, Any]] = []
            for expected_order, item in enumerate(raw_sessions, start=1):
                if item["execution_order"] != expected_order:
                    raise ValueError("execution order changed")
                session_date = validate_workout_date(item["date"], name="session date")
                if not week_start <= session_date <= week_end:
                    raise ValueError("session date left approved week")
                if item["purpose"] not in {"easy_run", "long_run"}:
                    raise ValueError("session purpose changed")
                definition = WorkoutDefinition.model_validate(
                    item["definition"], strict=True
                )
                aggregates = aggregate_workout(definition)
                if aggregates != item["aggregates"]:
                    raise ValueError("workout aggregates changed")
                sessions.append(
                    {
                        "execution_order": expected_order,
                        "date": session_date,
                        "purpose": item["purpose"],
                        "name": definition.name,
                        "definition": definition,
                        "aggregates": aggregates,
                    }
                )
            if [item["date"] for item in sessions] != sorted(
                item["date"] for item in sessions
            ):
                raise ValueError("session dates changed")
            return sessions
        except (KeyError, TypeError, ValueError) as exc:
            raise MalformedWeeklyPlanError(
                "Approved weekly proposal failed strict revalidation"
            ) from exc

    @staticmethod
    def _session_base(session: dict[str, Any]) -> dict[str, Any]:
        return {
            "execution_order": session["execution_order"],
            "date": session["date"],
            "purpose": session["purpose"],
            "name": session["name"],
            "aggregates": session["aggregates"],
        }

    def _unconfirmed_result(
        self, approval: _Approval, sessions: list[dict[str, Any]]
    ) -> dict[str, Any]:
        return {
            "week_start": approval.proposal["week_start"],
            "week_end": approval.proposal["week_end"],
            "proposal_fingerprint": approval.fingerprint,
            "requested_session_count": len(sessions),
            "completed_session_count": 0,
            "sessions": [
                {
                    **self._session_base(item),
                    "created": False,
                    "scheduled": False,
                    "safe_status": "not_started",
                    "uncertain": False,
                }
                for item in sessions
            ],
            "partial_failure": False,
            "uncertain": False,
            "remaining_sessions_not_attempted": len(sessions),
            "preview_only": True,
            "created": False,
            "scheduled": False,
            "next_action": (
                "No Garmin change occurred. Confirm this exact fingerprint once "
                "only after reviewing the full preview."
            ),
        }

    def _compact_outcome(
        self, session: dict[str, Any], outcome: dict[str, Any]
    ) -> dict[str, Any]:
        created = outcome.get("created") is True
        scheduled = outcome.get("scheduled") is True
        is_uncertain = bool(
            outcome.get("partial_failure")
            and "uncertain" in str(outcome.get("message", "")).casefold()
        )
        status = (
            "scheduled"
            if scheduled
            else "uncertain"
            if is_uncertain
            else "created_unscheduled"
            if created
            else "failed_not_created"
        )
        return {
            **self._session_base(session),
            "created": created,
            "scheduled": scheduled,
            "safe_status": status,
            "uncertain": is_uncertain,
        }

    def _failed_session(
        self,
        session: dict[str, Any],
        exc: WorkoutProviderError,
        uncertain: bool,
    ) -> dict[str, Any]:
        if uncertain:
            status = "uncertain"
            created: bool | None = None
            scheduled: bool | None = None
        else:
            status = "failed_not_created"
            created = False
            scheduled = False
        if isinstance(exc, WorkoutAuthenticationError):
            reason = "authentication_failed"
        elif isinstance(exc, WorkoutUnsupportedError):
            reason = "unsupported_client"
        elif isinstance(exc, WorkoutEndpointError):
            reason = "rate_limited" if "rate limit" in str(exc) else "endpoint_failed"
        elif isinstance(exc, WorkoutResponseError):
            reason = "malformed_or_uncertain_creation_response"
        else:
            reason = "uncertain_creation_result"
        return {
            **self._session_base(session),
            "created": created,
            "scheduled": scheduled,
            "safe_status": status,
            "uncertain": uncertain,
            "failure_reason": reason,
        }

    def _not_attempted(self, session: dict[str, Any]) -> dict[str, Any]:
        return {
            **self._session_base(session),
            "created": False,
            "scheduled": False,
            "safe_status": "not_attempted",
            "uncertain": False,
        }

    @staticmethod
    def _next_action(partial_failure: bool, uncertain: bool) -> str:
        if uncertain:
            return (
                "Stop. Inspect Garmin Connect manually before any further action; "
                "do not retry this approval."
            )
        if partial_failure:
            return (
                "Inspect Garmin Connect, preserve all completed or unscheduled "
                "workouts, and generate a new preview before further action."
            )
        return (
            "Inspect Garmin Connect and verify every workout and calendar assignment."
        )
