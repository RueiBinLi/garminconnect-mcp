from __future__ import annotations

import os
import sys
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from garminconnect import Garmin
from mcp.server.fastmcp import FastMCP

from .provider import GarminActivityProvider, GarminRecoveryProvider

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


def _summarize_items(
    data: Any, preferred_keys: tuple[str, ...], kind: str
) -> dict[str, Any]:
    items: list[Any] | None = None
    if isinstance(data, list):
        items = data
    elif isinstance(data, dict):
        for key in preferred_keys:
            value = data.get(key)
            if isinstance(value, list):
                items = value
                break
        if items is None:
            first_list = next(
                (value for value in data.values() if isinstance(value, list)), None
            )
            if isinstance(first_list, list):
                items = first_list

    if items is None:
        items = []

    summarizer = (
        _summarize_scheduled_workout
        if kind == "scheduled_workout"
        else _summarize_workout
    )
    summaries = [summarizer(item) for item in items if isinstance(item, dict)]
    return {"count": len(summaries), "items": summaries}


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
def garmin_workouts(start: int = 0, limit: int = 20) -> dict[str, Any]:
    """List saved Garmin workout templates with summarized fields."""
    return _summarize_items(
        _call("get_workouts", start, limit), ("workouts",), "workout"
    )


@mcp.tool()
def garmin_scheduled_workouts(year: int, month: int) -> dict[str, Any]:
    """List scheduled Garmin workouts for a calendar month using 1-12 months."""
    return _summarize_items(
        _call("get_scheduled_workouts", year, month),
        ("scheduledWorkouts", "workouts", "calendarItems"),
        "scheduled_workout",
    )


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
