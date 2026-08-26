from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from typing import Any, Literal, TypedDict

from .activities import NormalizedActivity, normalized_activity_date


class MeasurementCoverage(TypedDict):
    available_count: int
    unavailable_count: int
    complete: bool


class WeeklyRunningSummary(TypedDict):
    week_start: str
    week_end: str
    range_start: str
    range_end: str
    activity_count: int
    distance_m: float | None
    duration_s: float | None
    distance_coverage: MeasurementCoverage
    duration_coverage: MeasurementCoverage
    longest_run: NormalizedActivity | None


MeasurementField = Literal["distance_m", "duration_s"]


def _coverage(
    activities: list[NormalizedActivity], field: MeasurementField
) -> MeasurementCoverage:
    available = sum(activity[field] is not None for activity in activities)
    return {
        "available_count": available,
        "unavailable_count": len(activities) - available,
        "complete": available == len(activities),
    }


def _sum_measurement(
    activities: list[NormalizedActivity], field: MeasurementField
) -> float | None:
    values = [activity[field] for activity in activities if activity[field] is not None]
    if not activities:
        return 0.0
    if not values:
        return None
    return round(sum(values), 2)


def longest_run(activities: list[NormalizedActivity]) -> NormalizedActivity | None:
    """Select the greatest supplied distance, breaking ties by earliest start."""
    candidates = [item for item in activities if item["distance_m"] is not None]
    if not candidates:
        return None
    return min(
        candidates,
        key=lambda item: (
            -float(item["distance_m"]),
            item["start_time_local"] or item["start_time_gmt"] or "9999",
            item["activity_id"] or "",
        ),
    )


def summarize_running_weeks(
    activities: list[NormalizedActivity], start_date: str, end_date: str
) -> dict[str, Any]:
    """Aggregate normalized activities into Monday-based calendar weeks."""
    start = date.fromisoformat(start_date)
    end = date.fromisoformat(end_date)
    assigned: dict[date, list[NormalizedActivity]] = defaultdict(list)
    unassigned = 0
    for activity in activities:
        activity_day = normalized_activity_date(activity)
        if activity_day is None or not start <= activity_day <= end:
            unassigned += 1
            continue
        week_start = activity_day - timedelta(days=activity_day.weekday())
        assigned[week_start].append(activity)

    first_week = start - timedelta(days=start.weekday())
    summaries: list[WeeklyRunningSummary] = []
    week = first_week
    while week <= end:
        week_end = week + timedelta(days=6)
        items = assigned[week]
        summaries.append(
            {
                "week_start": week.isoformat(),
                "week_end": week_end.isoformat(),
                "range_start": max(start, week).isoformat(),
                "range_end": min(end, week_end).isoformat(),
                "activity_count": len(items),
                "distance_m": _sum_measurement(items, "distance_m"),
                "duration_s": _sum_measurement(items, "duration_s"),
                "distance_coverage": _coverage(items, "distance_m"),
                "duration_coverage": _coverage(items, "duration_s"),
                "longest_run": longest_run(items),
            }
        )
        week += timedelta(days=7)

    return {
        "start_date": start_date,
        "end_date": end_date,
        "week_definition": "Monday through Sunday",
        "activity_count": len(activities),
        "assigned_activity_count": len(activities) - unassigned,
        "unassigned_activity_count": unassigned,
        "longest_run": longest_run(activities),
        "weeks": summaries,
    }


def _delta(current: float | None, previous: float | None) -> float | None:
    if current is None or previous is None:
        return None
    return round(current - previous, 2)


def compare_week_summaries(
    previous: WeeklyRunningSummary, current: WeeklyRunningSummary
) -> dict[str, Any]:
    """Return factual absolute deltas; partial-input metadata stays visible."""
    return {
        "previous_week": previous,
        "current_week": current,
        "distance_change_m": _delta(current["distance_m"], previous["distance_m"]),
        "duration_change_s": _delta(current["duration_s"], previous["duration_s"]),
        "activity_count_change": current["activity_count"] - previous["activity_count"],
        "distance_comparison_complete": previous["distance_coverage"]["complete"]
        and current["distance_coverage"]["complete"],
        "duration_comparison_complete": previous["duration_coverage"]["complete"]
        and current["duration_coverage"]["complete"],
    }


def compare_recent_weekly_longest_runs(
    activities: list[NormalizedActivity], start_date: str, end_date: str, limit: int
) -> dict[str, Any]:
    """Compare each week's longest measured-distance run, newest first."""
    summary = summarize_running_weeks(activities, start_date, end_date)
    weekly = summary["weeks"]
    candidates = [week["longest_run"] for week in weekly if week["longest_run"]]
    candidates.reverse()
    latest = candidates[0] if candidates else None
    preceding = candidates[1 : limit + 1]
    comparisons = []
    if latest is not None:
        for prior in preceding:
            comparisons.append(
                {
                    "run": prior,
                    "distance_change_m": _delta(
                        latest["distance_m"], prior["distance_m"]
                    ),
                    "duration_change_s": _delta(
                        latest["duration_s"], prior["duration_s"]
                    ),
                }
            )
    return {
        "rule": "greatest supplied distance in each Monday-Sunday week",
        "week_count": len(weekly),
        "weeks_with_distance_candidate_count": len(candidates),
        "weeks_without_distance_candidate_count": len(weekly) - len(candidates),
        "unassigned_activity_count": summary["unassigned_activity_count"],
        "latest_long_run": latest,
        "preceding_long_run_count": len(preceding),
        "comparisons": comparisons,
    }
