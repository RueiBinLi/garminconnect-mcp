from __future__ import annotations

import os
import sys
from datetime import date, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from garminconnect import Garmin
from mcp.server.fastmcp import FastMCP
from pydantic import StrictBool, StrictInt

from .provider import (
    GarminActivityProvider,
    GarminRecoveryProvider,
    GarminWorkoutProvider,
    InvalidActivityRequestError,
    InvalidWorkoutRequestError,
)
from .training import (
    compare_recent_weekly_longest_runs,
    compare_week_summaries,
    summarize_running_weeks,
)
from .workout_builder import (
    WorkoutDefinition,
    aggregate_workout,
    preview_running_workout,
)

mcp = FastMCP("Garmin Connect")


def _env_path() -> Path:
    return Path(__file__).resolve().parents[2] / ".env"


def _today() -> str:
    return date.today().isoformat()


def _day_or_today(day: str | None) -> str:
    return _today() if day is None else day


def _token_dir() -> str:
    configured = os.getenv("GARMINCONNECT_TOKEN_DIR", "~/.garminconnect")
    return str(Path(configured).expanduser())


def _mfa_code() -> str:
    code = os.getenv("GARMIN_MFA_CODE")
    if code:
        return code

    if sys.stdin.isatty():
        code = input("Garmin MFA code: ").strip()

    if not code:
        raise RuntimeError(
            "Garmin MFA is required. Set GARMIN_MFA_CODE temporarily, or login "
            "once from an interactive terminal to create saved tokens."
        )
    return code


@lru_cache(maxsize=1)
def _client() -> Garmin:
    load_dotenv(_env_path())

    email = os.getenv("GARMIN_EMAIL")
    password = os.getenv("GARMIN_PASSWORD")

    client = Garmin(email, password, prompt_mfa=_mfa_code)
    client.login(_token_dir())
    return client


def _call(method_name: str, *args: Any, **kwargs: Any) -> Any:
    method = getattr(_client(), method_name)
    return method(*args, **kwargs)


def _call_first(method_names: tuple[str, ...], *args: Any, **kwargs: Any) -> Any:
    client = _client()
    missing: list[str] = []

    for method_name in method_names:
        method = getattr(client, method_name, None)
        if method is None:
            missing.append(method_name)
            continue
        return method(*args, **kwargs)

    raise AttributeError(f"None of these garminconnect methods exist: {missing}")


def _activity_provider() -> GarminActivityProvider:
    return GarminActivityProvider(_client)


def _recovery_provider() -> GarminRecoveryProvider:
    return GarminRecoveryProvider(_client)


def _workout_provider() -> GarminWorkoutProvider:
    return GarminWorkoutProvider(_client)


def _first_present(data: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        value = data.get(key)
        if value is not None:
            return value
    return None


def _find_first_key(data: Any, keys: tuple[str, ...]) -> Any:
    if isinstance(data, dict):
        found = _first_present(data, keys)
        if found is not None:
            return found
        for value in data.values():
            found = _find_first_key(value, keys)
            if found is not None:
                return found

    if isinstance(data, list):
        for item in data:
            found = _find_first_key(item, keys)
            if found is not None:
                return found

    return None


def _sport_type_key(value: Any) -> str | None:
    if isinstance(value, dict):
        sport = _first_present(value, ("sportTypeKey", "key", "typeKey"))
        return str(sport) if sport is not None else None
    return str(value) if value is not None else None


def _summarize_workout(workout: dict[str, Any]) -> dict[str, Any]:
    sport_type = _first_present(workout, ("sportType", "activityType", "sport"))

    return {
        "workout_id": _first_present(workout, ("workoutId", "id")),
        "name": _first_present(workout, ("workoutName", "name")),
        "sport_type": _sport_type_key(sport_type),
        "estimated_duration_secs": _first_present(
            workout, ("estimatedDurationInSecs", "estimatedDurationSecs", "duration")
        ),
    }


def _summarize_scheduled_workout(workout: dict[str, Any]) -> dict[str, Any]:
    template = workout.get("workout")
    if not isinstance(template, dict):
        template = workout

    return {
        "scheduled_workout_id": _first_present(
            workout,
            (
                "scheduledWorkoutId",
                "workoutScheduleId",
                "calendarScheduleId",
                "id",
            ),
        ),
        "date": _first_present(
            workout, ("date", "scheduleDate", "workoutScheduleDate", "calendarDate")
        ),
        **_summarize_workout(template),
    }


@mcp.tool()
def garmin_connection_status() -> dict[str, bool]:
    """Check Garmin Connect login without returning personal data."""
    _client()
    return {"ok": True}


@mcp.tool()
def garmin_ping() -> dict[str, bool]:
    """Check Garmin Connect login without returning personal data."""
    _client()
    return {"ok": True}


@mcp.tool()
def garmin_profile() -> dict[str, Any]:
    """Get the raw private Garmin Connect user profile."""
    profile = _call("get_user_profile")
    full_name = _call("get_full_name")
    return {"full_name": full_name, "profile": profile}


@mcp.tool()
def garmin_daily_stats(day: str | None = None) -> dict[str, Any]:
    """Get compact normalized daily statistics for a YYYY-MM-DD date.

    Durations use seconds, distance uses meters, energy uses kcal, and heart
    rate uses bpm. Stress and Body Battery retain Garmin's native scales.
    Missing Garmin fields are null. This tool is read-only.
    """
    return _recovery_provider().daily_statistics(_day_or_today(day))


@mcp.tool()
def garmin_heart_rate(day: str | None = None) -> dict[str, Any]:
    """Get normalized daily and resting heart-rate summaries in bpm.

    The date must use YYYY-MM-DD. Per-sample heart-rate data is discarded,
    unavailable fields are null, and this tool is read-only.
    """
    return _recovery_provider().heart_rate(_day_or_today(day))


@mcp.tool()
def garmin_sleep(day: str | None = None) -> dict[str, Any]:
    """Get normalized sleep for a YYYY-MM-DD date.

    Sleep and stage durations use seconds. Times are UTC ISO 8601 strings.
    Garmin score/status fields are factual values, missing fields are null,
    and detailed sample arrays are discarded. This tool is read-only.
    """
    return _recovery_provider().sleep(_day_or_today(day))


@mcp.tool()
def garmin_hrv(day: str | None = None) -> dict[str, Any]:
    """Get normalized nightly HRV summary values in milliseconds.

    The date must use YYYY-MM-DD. Garmin's status is returned without medical
    interpretation, unavailable fields are null, and this tool is read-only.
    """
    return _recovery_provider().hrv(_day_or_today(day))


@mcp.tool()
def garmin_hrv_range(start_date: str, end_date: str) -> dict[str, Any]:
    """Get normalized HRV summaries for an inclusive range of up to 14 days.

    Dates must use YYYY-MM-DD. Values use milliseconds, missing days are
    omitted by Garmin, unavailable fields are null, and this tool is read-only.
    """
    items = _recovery_provider().hrv_range(start_date, end_date)
    return {
        "start_date": start_date,
        "end_date": end_date,
        "count": len(items),
        "items": items,
    }


@mcp.tool()
def garmin_body_battery(day: str | None = None) -> dict[str, Any]:
    """Get normalized Body Battery summary values for a YYYY-MM-DD date.

    Values retain Garmin's native scale. Sample timestamps and event details
    are discarded, unavailable fields are null, and this tool is read-only.
    """
    return _recovery_provider().body_battery(_day_or_today(day))


@mcp.tool()
def garmin_stress(day: str | None = None) -> dict[str, Any]:
    """Get normalized daily stress summary values for a YYYY-MM-DD date.

    Values retain Garmin's native scale. Per-sample stress and Body Battery
    data are discarded, unavailable fields are null, and this tool is read-only.
    """
    return _recovery_provider().stress(_day_or_today(day))


@mcp.tool()
def garmin_recent_activities(
    start: int = 0, limit: int = 10, running_only: bool = False
) -> dict[str, Any]:
    """List normalized activities; start >= 0 and limit is 1-100.

    Set running_only to filter at Garmin's activity endpoint. Returned measurements
    use meters, seconds, seconds per kilometer, bpm, and spm. Missing fields are null.
    This tool is read-only.
    """
    items = _activity_provider().recent_activities(
        start=start, limit=limit, running_only=running_only
    )
    return {
        "start": start,
        "limit": limit,
        "running_only": running_only,
        "count": len(items),
        "items": items,
    }


@mcp.tool()
def garmin_activity(activity_id: str) -> dict[str, Any]:
    """Get one normalized activity by numeric ID; this tool is read-only.

    Returned measurements use meters, seconds, seconds per kilometer, bpm, and
    spm. Missing Garmin fields are returned as null.
    """
    return _activity_provider().activity(activity_id)


@mcp.tool()
def garmin_running_activities_by_date(start_date: str, end_date: str) -> dict[str, Any]:
    """List normalized runs in an inclusive YYYY-MM-DD range of at most 42 days.

    Measurements use meters, seconds, seconds per kilometer, bpm, spm, and
    meters of elevation gain. Missing fields are null. The Garmin endpoint is
    running-filtered and results are checked again after normalization. Read-only.
    """
    items = _activity_provider().running_activities_by_date(start_date, end_date)
    return {
        "start_date": start_date,
        "end_date": end_date,
        "inclusive": True,
        "count": len(items),
        "items": items,
    }


@mcp.tool()
def garmin_weekly_running_summary(start_date: str, end_date: str) -> dict[str, Any]:
    """Summarize runs by Monday-Sunday week for an inclusive range up to 42 days.

    Dates require strict YYYY-MM-DD. Totals use distance_m and duration_s;
    counts and coverage show missing measurements. A total is null when every
    activity lacks that measurement, while an empty week totals zero. Longest
    runs require supplied distance. No interpretation is added. Read-only.
    """
    items = _activity_provider().running_activities_by_date(start_date, end_date)
    return summarize_running_weeks(items, start_date, end_date)


@mcp.tool()
def garmin_compare_running_weeks(
    current_week_start: str, previous_week_start: str
) -> dict[str, Any]:
    """Compare two adjacent Monday-Sunday running weeks using YYYY-MM-DD starts.

    The previous start must be exactly seven days before the current start.
    Distance changes use meters and duration changes use seconds. Coverage
    flags expose partial totals caused by unavailable fields. Read-only.
    """
    try:
        current = date.fromisoformat(current_week_start)
        previous = date.fromisoformat(previous_week_start)
    except (TypeError, ValueError):
        current = previous = date.min
    if (
        current.isoformat() != current_week_start
        or previous.isoformat() != previous_week_start
        or current.weekday() != 0
        or previous.weekday() != 0
    ):
        raise InvalidActivityRequestError(
            "week starts must be valid YYYY-MM-DD Mondays"
        )
    if previous + timedelta(days=7) != current:
        raise InvalidActivityRequestError(
            "previous_week_start must be exactly seven days before current_week_start"
        )

    end_date = (current + timedelta(days=6)).isoformat()
    items = _activity_provider().running_activities_by_date(
        previous_week_start, end_date
    )
    weeks = summarize_running_weeks(items, previous_week_start, end_date)["weeks"]
    return compare_week_summaries(weeks[0], weeks[1])


@mcp.tool()
def garmin_compare_recent_long_runs(end_date: str, limit: int = 3) -> dict[str, Any]:
    """Compare the latest weekly longest run with up to 1-4 preceding candidates.

    The lookback covers the current partial week plus limit preceding calendar
    weeks and ends on strict YYYY-MM-DD end_date (at most 35 days for limit 4).
    A long run is the greatest supplied distance_m in a Monday-Sunday week;
    distance changes use meters and duration changes use seconds. Weeks without
    supplied distance have no candidate, and unavailable duration changes are
    null. This is factual and read-only.
    """
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 4:
        raise InvalidActivityRequestError("limit must be between 1 and 4")
    try:
        end = date.fromisoformat(end_date)
    except (TypeError, ValueError):
        end = date.min
    if end.isoformat() != end_date:
        raise InvalidActivityRequestError("end_date must use valid YYYY-MM-DD format")
    try:
        current_week_start = end - timedelta(days=end.weekday())
        start_date = (current_week_start - timedelta(days=limit * 7)).isoformat()
    except OverflowError as exc:
        raise InvalidActivityRequestError(
            "end_date is too early for the requested comparison range"
        ) from exc
    items = _activity_provider().running_activities_by_date(start_date, end_date)
    result = compare_recent_weekly_longest_runs(items, start_date, end_date, limit)
    return {
        "start_date": start_date,
        "end_date": end_date,
        "requested_preceding_limit": limit,
        **result,
    }


@mcp.tool()
def garmin_workouts(
    start: StrictInt = 0, limit: StrictInt = 20, running_only: StrictBool = False
) -> dict[str, Any]:
    """List one read-only page of compact saved Garmin workout templates.

    start is a zero-based public offset; limit is 1-100. The provider translates
    this to Garmin's current My Workouts pagination and running_only sport filter,
    then defensively checks normalized sport types. Results use Garmin's updated-
    date-descending UI order. Duration uses seconds and distance uses meters;
    unavailable fields are null. Raw steps are discarded.
    """
    source_count, items = _workout_provider().saved_workouts(
        start=start, limit=limit, running_only=running_only
    )
    return {
        "start": start,
        "limit": limit,
        "running_only": running_only,
        "source_count": source_count,
        "count": len(items),
        "items": items,
    }


@mcp.tool()
def garmin_scheduled_workouts(start_date: str, end_date: str) -> dict[str, Any]:
    """List read-only scheduled workouts in an inclusive range up to 31 days.

    Dates must be strict YYYY-MM-DD Garmin calendar dates. The provider fetches
    the intersecting Garmin calendar month(s), discards non-workout items, and
    orders results by scheduled date and IDs. Dates are date-only: no timezone
    or instant is inferred. Duration uses seconds, distance uses meters,
    unavailable fields are null, and raw calendar/step payloads are discarded.
    """
    items = _workout_provider().scheduled_workouts(start_date, end_date)
    return {
        "start_date": start_date,
        "end_date": end_date,
        "inclusive": True,
        "count": len(items),
        "items": items,
    }


@mcp.tool()
def garmin_preview_running_workout(
    definition: WorkoutDefinition,
) -> dict[str, Any]:
    """Validate and preview a structured running workout entirely offline.

    Public measurements use duration_s, distance_m, heart_rate_bpm, and
    pace_s_per_km fields. Supported executable steps are warmup, run, recovery,
    and cooldown; bounded repeat groups may nest up to two levels. This tool
    performs no Garmin client or network call, exposes no Garmin JSON payload,
    and does not upload, create, schedule, modify, or delete anything.
    """
    if not isinstance(definition, WorkoutDefinition):
        definition = WorkoutDefinition.model_validate(definition, strict=True)
    return preview_running_workout(definition)


@mcp.tool()
def garmin_create_running_workout(
    definition: WorkoutDefinition, confirmed: StrictBool = False
) -> dict[str, Any]:
    """Create exactly one validated running workout, without scheduling it.

    The definition uses the same strict schema and explicit units as
    garmin_preview_running_workout. The default confirmed=false performs no
    Garmin client or network call. Set confirmed=true only after reviewing the
    exact preview. A confirmed call uploads once, does not retry, and cannot
    schedule, modify, unschedule, delete, or push a workout to a device.
    """
    if not isinstance(definition, WorkoutDefinition):
        definition = WorkoutDefinition.model_validate(definition, strict=True)
    if not isinstance(confirmed, bool):
        raise InvalidWorkoutRequestError("confirmed must be a boolean")
    if not confirmed:
        aggregates = aggregate_workout(definition)
        return {
            "created": False,
            "workout_id": None,
            "name": definition.name,
            "sport_type": definition.sport_type,
            "total_duration_s": aggregates["total_duration_s"],
            "total_distance_m": aggregates["total_distance_m"],
            "scheduled": False,
            "message": (
                "Not created; preview the validated workout, then call again with "
                "confirmed=true to create exactly one unscheduled workout."
            ),
        }
    return _workout_provider().create_running_workout(definition)


@mcp.tool()
def garmin_schedule_workout(workout_id: str, day: str) -> dict[str, Any]:
    """Schedule an existing Garmin workout template on a YYYY-MM-DD date."""
    result = _call("schedule_workout", workout_id, day)
    summary = (
        _summarize_scheduled_workout(result)
        if isinstance(result, dict)
        else {"scheduled_workout_id": None, "date": day, "workout_id": workout_id}
    )
    summary["scheduled"] = True
    return summary


@mcp.tool()
def garmin_create_scheduled_workout(
    workout_json: dict[str, Any] | list[Any] | str, day: str
) -> dict[str, Any]:
    """Upload a Garmin workout JSON payload, then schedule it on a YYYY-MM-DD date."""
    uploaded = _call("upload_workout", workout_json)
    workout_id = _find_first_key(uploaded, ("workoutId", "workout_id", "id"))
    if workout_id is None:
        raise ValueError("Garmin upload response did not include a workout ID")

    scheduled = _call("schedule_workout", workout_id, day)
    summary = (
        _summarize_scheduled_workout(scheduled)
        if isinstance(scheduled, dict)
        else {"scheduled_workout_id": None, "date": day, "workout_id": workout_id}
    )
    summary["uploaded_workout_id"] = workout_id
    summary["scheduled"] = True
    return summary


@mcp.tool()
def garmin_unschedule_workout(scheduled_workout_id: str) -> dict[str, Any]:
    """Remove a Garmin workout from the calendar without deleting the template."""
    _call("unschedule_workout", scheduled_workout_id)
    return {"unscheduled": True, "scheduled_workout_id": scheduled_workout_id}


def login_once() -> dict[str, bool]:
    _client()
    return {"ok": True}


def main(argv: list[str] | None = None) -> None:
    args = sys.argv[1:] if argv is None else argv
    if args == ["login"]:
        login_once()
        print(f"Garmin login ok. Tokens stored in {_token_dir()}.")
        return
    if args and args != ["serve"]:
        raise SystemExit("usage: garminconnect-mcp [serve|login]")
    mcp.run()


if __name__ == "__main__":
    main()
