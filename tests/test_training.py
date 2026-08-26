from __future__ import annotations

from typing import Any

from garminconnect_mcp.activities import NormalizedActivity
from garminconnect_mcp.training import (
    compare_recent_weekly_longest_runs,
    compare_week_summaries,
    longest_run,
    summarize_running_weeks,
)


def run(
    activity_id: str,
    day: str | None,
    *,
    distance_m: float | None,
    duration_s: float | None,
) -> NormalizedActivity:
    return {
        "activity_id": activity_id,
        "start_time_local": f"{day} 06:00:00" if day else None,
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


def test_weekly_summary_reports_partial_coverage_and_empty_weeks() -> None:
    activities = [
        run("1", "2030-04-01", distance_m=5000, duration_s=1500),
        run("2", "2030-04-03", distance_m=None, duration_s=1800),
        run("3", "2030-04-15", distance_m=8000, duration_s=None),
        run("4", None, distance_m=1000, duration_s=300),
    ]

    result = summarize_running_weeks(activities, "2030-04-01", "2030-04-21")

    assert result["activity_count"] == 4
    assert result["assigned_activity_count"] == 3
    assert result["unassigned_activity_count"] == 1
    assert result["longest_run"]["activity_id"] == "3"
    first, empty, third = result["weeks"]
    assert first["distance_m"] == 5000.0
    assert first["duration_s"] == 3300.0
    assert first["activity_count"] == 2
    assert first["distance_coverage"] == {
        "available_count": 1,
        "unavailable_count": 1,
        "complete": False,
    }
    assert empty["activity_count"] == 0
    assert empty["distance_m"] == 0.0
    assert empty["duration_s"] == 0.0
    assert empty["distance_coverage"]["complete"] is True
    assert third["duration_s"] is None
    assert third["duration_coverage"]["complete"] is False


def test_longest_run_requires_distance_and_has_deterministic_tie_break() -> None:
    activities = [
        run("2", "2030-04-02", distance_m=10000, duration_s=3600),
        run("1", "2030-04-01", distance_m=10000, duration_s=3500),
        run("3", "2030-04-03", distance_m=None, duration_s=4000),
    ]

    assert longest_run(activities)["activity_id"] == "1"  # type: ignore[index]
    assert longest_run([activities[2]]) is None


def test_week_comparison_keeps_partial_status_visible() -> None:
    summary = summarize_running_weeks(
        [
            run("1", "2030-04-01", distance_m=5000, duration_s=1500),
            run("2", "2030-04-08", distance_m=7000, duration_s=None),
        ],
        "2030-04-01",
        "2030-04-14",
    )

    result = compare_week_summaries(*summary["weeks"])

    assert result["distance_change_m"] == 2000.0
    assert result["duration_change_s"] is None
    assert result["activity_count_change"] == 0
    assert result["distance_comparison_complete"] is True
    assert result["duration_comparison_complete"] is False


def test_recent_long_runs_uses_one_distance_winner_per_week() -> None:
    activities = [
        run("1", "2030-04-01", distance_m=6000, duration_s=1800),
        run("2", "2030-04-02", distance_m=9000, duration_s=3000),
        run("3", "2030-04-09", distance_m=10000, duration_s=None),
        run("4", "2030-04-16", distance_m=12000, duration_s=3900),
    ]

    result: dict[str, Any] = compare_recent_weekly_longest_runs(
        activities, "2030-04-01", "2030-04-21", 2
    )

    assert result["latest_long_run"]["activity_id"] == "4"
    assert result["week_count"] == 3
    assert result["weeks_with_distance_candidate_count"] == 3
    assert result["weeks_without_distance_candidate_count"] == 0
    assert result["unassigned_activity_count"] == 0
    assert [item["run"]["activity_id"] for item in result["comparisons"]] == [
        "3",
        "2",
    ]
    assert result["comparisons"][0]["distance_change_m"] == 2000.0
    assert result["comparisons"][0]["duration_change_s"] is None


def test_recent_long_runs_handles_no_distance_candidates() -> None:
    result = compare_recent_weekly_longest_runs(
        [run("1", "2030-04-01", distance_m=None, duration_s=1200)],
        "2030-04-01",
        "2030-04-07",
        3,
    )

    assert result["latest_long_run"] is None
    assert result["weeks_with_distance_candidate_count"] == 0
    assert result["weeks_without_distance_candidate_count"] == 1
    assert result["preceding_long_run_count"] == 0
    assert result["comparisons"] == []
