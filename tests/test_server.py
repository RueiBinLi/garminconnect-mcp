from __future__ import annotations

import anyio
import pytest
from mcp.server.fastmcp.exceptions import ToolError

from garminconnect_mcp import server
from garminconnect_mcp.provider import (
    InvalidActivityRequestError,
    InvalidRecoveryRequestError,
)


class FakeDate:
    @classmethod
    def today(cls) -> object:
        return cls()

    def isoformat(self) -> str:
        return "2026-05-21"


class FakeStdin:
    def __init__(self, is_tty: bool) -> None:
        self._is_tty = is_tty

    def isatty(self) -> bool:
        return self._is_tty


class FakeClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[object, ...], dict[str, object]]] = []

    def _record(
        self, method: str, *args: object, **kwargs: object
    ) -> dict[str, object]:
        self.calls.append((method, args, kwargs))
        return {"method": method, "args": args, "kwargs": kwargs}

    def get_user_profile(self) -> dict[str, object]:
        self.calls.append(("get_user_profile", (), {}))
        return {"userName": "runner"}

    def get_full_name(self) -> str:
        self.calls.append(("get_full_name", (), {}))
        return "Runner Example"

    def get_stats(self, cdate: str) -> dict[str, object]:
        self.calls.append(("get_stats", (cdate,), {}))
        return {"calendarDate": cdate, "totalSteps": 1234}

    def get_heart_rates(self, cdate: str) -> dict[str, object]:
        self.calls.append(("get_heart_rates", (cdate,), {}))
        return {"calendarDate": cdate, "restingHeartRate": 50}

    def get_sleep_data(self, cdate: str) -> dict[str, object]:
        self.calls.append(("get_sleep_data", (cdate,), {}))
        return {"dailySleepDTO": {"calendarDate": cdate, "sleepTimeSeconds": 1}}

    def get_hrv_data(self, cdate: str) -> dict[str, object]:
        self.calls.append(("get_hrv_data", (cdate,), {}))
        return {"hrvSummary": {"calendarDate": cdate, "lastNightAvg": 1}}

    def get_hrv_data_range(self, start: str, end: str) -> dict[str, object]:
        self.calls.append(("get_hrv_data_range", (start, end), {}))
        return {
            "hrvSummaries": [
                {"calendarDate": start, "lastNightAvg": 1},
                {"calendarDate": end, "lastNightAvg": 2},
            ]
        }

    def get_body_battery(
        self, startdate: str, enddate: str | None = None
    ) -> list[dict[str, object]]:
        self.calls.append(("get_body_battery", (startdate,), {}))
        return [{"date": startdate, "charged": 1, "bodyBatteryValuesArray": []}]

    def get_stress_data(self, cdate: str) -> dict[str, object]:
        self.calls.append(("get_stress_data", (cdate,), {}))
        return {"calendarDate": cdate, "avgStressLevel": 1}

    def get_heart_rate_zones(self) -> list[dict[str, object]]:
        self.calls.append(("get_heart_rate_zones", (), {}))
        return [
            {
                "sport": "RUNNING",
                "trainingMethod": "LTHR",
                "maxHeartRateUsed": 190,
                "restingHeartRateUsed": 50,
                "lactateThresholdHeartRateUsed": 170,
                "zone1Floor": 100,
                "zone2Floor": 120,
                "zone3Floor": 140,
                "zone4Floor": 160,
                "zone5Floor": 175,
            }
        ]

    def get_activities(
        self,
        start: int = 0,
        limit: int = 20,
        activitytype: str | None = None,
    ) -> list[dict[str, object]]:
        self.calls.append(
            ("get_activities", (start, limit), {"activitytype": activitytype})
        )
        return [
            {
                "activityId": 123,
                "activityType": {"typeKey": "running"},
                "distance": 5000.0,
                "duration": 1500.0,
                "averageSpeed": 3.333333333,
            }
        ]

    def get_activities_by_date(
        self,
        startdate: str,
        enddate: str | None = None,
        activitytype: str | None = None,
        sortorder: str | None = None,
    ) -> list[dict[str, object]]:
        self.calls.append(
            (
                "get_activities_by_date",
                (startdate, enddate),
                {"activitytype": activitytype, "sortorder": sortorder},
            )
        )
        return [
            {
                "activityId": 123,
                "startTimeLocal": f"{startdate} 06:00:00",
                "activityType": {"typeKey": "running"},
                "distance": 5000.0,
                "duration": 1500.0,
            }
        ]

    def get_activity_details(self, activity_id: str) -> dict[str, object]:
        return self._record("get_activity_details", activity_id)

    def get_activity(self, activity_id: str) -> dict[str, object]:
        self.calls.append(("get_activity", (activity_id,), {}))
        return {
            "activityId": activity_id,
            "activityName": "Synthetic Run",
            "activityType": {"typeKey": "running"},
        }

    def get_workouts(self, start: int = 0, limit: int = 100) -> list[dict[str, object]]:
        self.calls.append(("get_workouts", (start, limit), {}))
        return [
            {
                "workoutId": 456,
                "workoutName": "Easy Run",
                "sportType": {"sportTypeKey": "running"},
                "description": None,
                "estimatedDurationInSecs": 1800,
                "estimatedDistanceInMeters": None,
            }
        ]

    def connectapi(self, path: str, **kwargs: object) -> object:
        if path == "/workout-service/workouts":
            result = self.get_workouts()
            self.calls[-1] = ("connectapi", (path,), kwargs)
            return result
        raise AssertionError(f"unexpected synthetic path: {path}")

    def get_scheduled_workouts(self, year: int, month: int) -> dict[str, object]:
        self.calls.append(("get_scheduled_workouts", (year, month), {}))
        return {
            "scheduledWorkouts": [
                {
                    "scheduledWorkoutId": 789,
                    "date": "2026-05-24",
                    "workout": {
                        "workoutId": 456,
                        "workoutName": "Easy Run",
                        "sportType": {"sportTypeKey": "running"},
                    },
                }
            ]
        }

    def schedule_workout(
        self, workout_id: str | int, date_str: str
    ) -> dict[str, object]:
        self.calls.append(("schedule_workout", (workout_id, date_str), {}))
        return {
            "scheduledWorkoutId": 789,
            "date": date_str,
            "workout": {
                "workoutId": workout_id,
                "workoutName": "Easy Run",
                "sportType": {"sportTypeKey": "running"},
            },
        }

    def get_scheduled_workout_by_id(
        self, scheduled_workout_id: str
    ) -> dict[str, object]:
        self.calls.append(("get_scheduled_workout_by_id", (scheduled_workout_id,), {}))
        return {
            "scheduledWorkoutId": scheduled_workout_id,
            "date": "2026-05-24",
            "workout": {
                "workoutId": 456,
                "workoutName": "Easy Run",
                "sportType": {"sportTypeKey": "running"},
            },
        }

    def upload_workout(self, workout_json: object) -> dict[str, object]:
        self.calls.append(("upload_workout", (workout_json,), {}))
        return {
            "workoutId": 456,
            "workoutName": "Easy Run",
            "sportType": {"sportTypeKey": "running"},
        }

    def unschedule_workout(self, scheduled_workout_id: str) -> None:
        self.calls.append(("unschedule_workout", (scheduled_workout_id,), {}))


@pytest.fixture
def fake_client(monkeypatch: pytest.MonkeyPatch) -> FakeClient:
    client = FakeClient()
    monkeypatch.setattr(server, "_client", lambda: client)
    return client


def test_token_dir_expands_home(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GARMINCONNECT_TOKEN_DIR", "~/garmin-tokens")

    assert server._token_dir().endswith("/garmin-tokens")
    assert "~" not in server._token_dir()


def test_env_path_uses_repo_root() -> None:
    assert server._env_path().name == ".env"
    assert server._env_path().parent.name == "garminconnect-mcp"


def test_mfa_code_requires_environment_or_tty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GARMIN_MFA_CODE", raising=False)
    monkeypatch.setattr(server.sys, "stdin", FakeStdin(False))

    with pytest.raises(RuntimeError, match="Garmin MFA is required"):
        server._mfa_code()


def test_mfa_code_reads_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GARMIN_MFA_CODE", "123456")

    assert server._mfa_code() == "123456"


def test_mfa_code_prompts_in_interactive_terminal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("GARMIN_MFA_CODE", raising=False)
    monkeypatch.setattr(server.sys, "stdin", FakeStdin(True))
    monkeypatch.setattr("builtins.input", lambda prompt: " 654321 ")

    assert server._mfa_code() == "654321"


def test_call_first_uses_first_existing_method(fake_client: FakeClient) -> None:
    result = server._call_first(
        ("missing_method", "get_activity_details"), "9000000000"
    )

    assert result == {
        "method": "get_activity_details",
        "args": ("9000000000",),
        "kwargs": {},
    }
    assert fake_client.calls == [("get_activity_details", ("9000000000",), {})]


def test_call_first_raises_when_no_method_exists(fake_client: FakeClient) -> None:
    with pytest.raises(AttributeError, match="None of these"):
        server._call_first(("missing_one", "missing_two"))

    assert fake_client.calls == []


def test_garmin_connection_status_checks_client_without_data_call(
    fake_client: FakeClient,
) -> None:
    assert server.garmin_connection_status() == {"ok": True}
    assert fake_client.calls == []


def test_garmin_ping_checks_client_without_data_call(fake_client: FakeClient) -> None:
    assert server.garmin_ping() == {"ok": True}
    assert fake_client.calls == []


def test_garmin_profile_combines_name_and_profile(fake_client: FakeClient) -> None:
    assert server.garmin_profile() == {
        "full_name": "Runner Example",
        "profile": {"userName": "runner"},
    }
    assert fake_client.calls == [
        ("get_user_profile", (), {}),
        ("get_full_name", (), {}),
    ]


def test_date_defaulted_tools_use_today(
    monkeypatch: pytest.MonkeyPatch, fake_client: FakeClient
) -> None:
    monkeypatch.setattr(server, "date", FakeDate)

    assert server.garmin_daily_stats()["date"] == "2026-05-21"
    assert server.garmin_heart_rate()["date"] == "2026-05-21"
    assert server.garmin_sleep()["date"] == "2026-05-21"
    assert server.garmin_hrv()["date"] == "2026-05-21"
    assert server.garmin_body_battery()["date"] == "2026-05-21"
    assert server.garmin_stress()["date"] == "2026-05-21"

    assert [call[0] for call in fake_client.calls] == [
        "get_stats",
        "get_heart_rates",
        "get_sleep_data",
        "get_hrv_data",
        "get_body_battery",
        "get_stress_data",
    ]


def test_explicit_empty_recovery_date_is_rejected_before_call(
    fake_client: FakeClient,
) -> None:
    with pytest.raises(InvalidRecoveryRequestError, match="YYYY-MM-DD"):
        server.garmin_sleep("")
    assert fake_client.calls == []


def test_tools_pass_explicit_arguments(fake_client: FakeClient) -> None:
    assert server.garmin_daily_stats("2026-05-20")["date"] == "2026-05-20"
    activities = server.garmin_recent_activities(start=5, limit=2)
    activity = server.garmin_activity("987")

    assert activities["start"] == 5
    assert activities["limit"] == 2
    assert activities["count"] == 1
    assert activities["items"][0]["activity_id"] == "123"
    assert activities["items"][0]["pace_s_per_km"] == 300.0
    assert activity["activity_id"] == "987"
    assert activity["name"] == "Synthetic Run"

    assert fake_client.calls == [
        ("get_stats", ("2026-05-20",), {}),
        ("get_activities", (5, 2), {"activitytype": None}),
        ("get_activity", ("987",), {}),
    ]


def test_new_activity_tools_return_compact_provider_results(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class ReadOnlyActivityProvider:
        def activity_temperature(self, activity_id: str) -> object:
            assert activity_id == "987"
            return {
                "activity_id": "987",
                "average_temperature_c": 21.0,
                "minimum_temperature_c": 19.0,
                "maximum_temperature_c": 23.0,
                "sample_count": 3,
                "source": "garmin_activity_detail_directAirTemperature",
                "warnings": [],
            }

        def activity_weather(self, activity_id: str) -> object:
            assert activity_id == "987"
            return {
                "activity_id": "987",
                "observed_at": "2030-04-12T06:15:00+08:00",
                "temperature": 24.0,
                "weather_station_present": True,
                "weather_station_timezone": "Asia/Example",
                "source": "garmin_activity_weather_station",
                "units_verified": False,
            }

        def activity_splits(self, activity_id: str, *, mode: str) -> object:
            assert (activity_id, mode) == ("987", "laps")
            return {
                "activity_id": "987",
                "split_type": "lap",
                "splits": [{"split_index": 1, "distance_m": 1000.0}],
            }

        def aerobic_drift(self, activity_id: str) -> object:
            assert activity_id == "987"
            return {
                "activity_id": "987",
                "method": "distance_halves_time_weighted_speed_hr_efficiency",
                "usable_for_drift_analysis": True,
                "aerobic_decoupling_pct": 1.25,
                "sample_count": 100,
                "warnings": [],
            }

    activity_provider = ReadOnlyActivityProvider()
    monkeypatch.setattr(server, "_activity_provider", lambda: activity_provider)

    temperature = server.garmin_activity_temperature("987")
    weather = server.garmin_activity_weather("987")
    splits = server.garmin_activity_splits("987")
    drift = server.garmin_activity_aerobic_drift("987")

    assert temperature["average_temperature_c"] == 21.0
    assert temperature["sample_count"] == 3
    assert weather["temperature"] == 24.0
    assert weather["units_verified"] is False
    assert splits["split_type"] == "lap"
    assert splits["splits"][0]["distance_m"] == 1000.0
    assert drift["aerobic_decoupling_pct"] == 1.25


@pytest.mark.parametrize(
    ("tool_name", "arguments"),
    [
        ("garmin_activity_splits", {"activity_id": 987}),
        ("garmin_activity_splits", {"activity_id": "987", "mode": 1}),
        ("garmin_activity_splits", {"activity_id": "987", "unknown": True}),
        ("garmin_activity_aerobic_drift", {"activity_id": 987}),
        ("garmin_activity_aerobic_drift", {"activity_id": "987", "unknown": True}),
        ("garmin_activity_temperature", {"activity_id": 987}),
        ("garmin_activity_temperature", {"activity_id": "987", "unknown": True}),
        ("garmin_activity_weather", {"activity_id": 987}),
        ("garmin_activity_weather", {"activity_id": "987", "unknown": True}),
    ],
)
def test_new_activity_tools_reject_invalid_mcp_arguments_before_provider(
    monkeypatch: pytest.MonkeyPatch,
    tool_name: str,
    arguments: dict[str, object],
) -> None:
    calls = 0

    def forbidden_provider() -> object:
        nonlocal calls
        calls += 1
        raise AssertionError("provider must not be constructed")

    monkeypatch.setattr(server, "_activity_provider", forbidden_provider)

    async def call_tool() -> None:
        await server.mcp.call_tool(tool_name, arguments)

    with pytest.raises(ToolError):
        anyio.run(call_tool)
    assert calls == 0


def test_hrv_range_returns_bounded_normalized_envelope(
    fake_client: FakeClient,
) -> None:
    assert server.garmin_hrv_range("2026-05-19", "2026-05-20") == {
        "start_date": "2026-05-19",
        "end_date": "2026-05-20",
        "count": 2,
        "items": [
            {
                "date": "2026-05-19",
                "weekly_average_ms": None,
                "last_night_average_ms": 1.0,
                "last_night_five_minute_high_ms": None,
                "status": None,
            },
            {
                "date": "2026-05-20",
                "weekly_average_ms": None,
                "last_night_average_ms": 2.0,
                "last_night_five_minute_high_ms": None,
                "status": None,
            },
        ],
    }
    assert fake_client.calls == [
        ("get_hrv_data_range", ("2026-05-19", "2026-05-20"), {})
    ]


def test_recent_activities_requests_running_filter(fake_client: FakeClient) -> None:
    result = server.garmin_recent_activities(limit=5, running_only=True)

    assert result["running_only"] is True
    assert result["count"] == 1
    assert fake_client.calls == [
        ("get_activities", (0, 5), {"activitytype": "running"})
    ]


def test_running_activities_by_date_returns_normalized_range(
    fake_client: FakeClient,
) -> None:
    result = server.garmin_running_activities_by_date("2030-04-01", "2030-04-07")

    assert result["inclusive"] is True
    assert result["count"] == 1
    assert result["items"][0]["distance_m"] == 5000.0
    assert fake_client.calls == [
        (
            "get_activities_by_date",
            ("2030-04-01", "2030-04-07"),
            {"activitytype": "running", "sortorder": "asc"},
        )
    ]


def test_weekly_summary_and_comparison_use_only_activity_date_endpoint(
    fake_client: FakeClient,
) -> None:
    summary = server.garmin_weekly_running_summary("2030-04-01", "2030-04-07")
    comparison = server.garmin_compare_running_weeks("2030-04-08", "2030-04-01")

    assert summary["weeks"][0]["distance_m"] == 5000.0
    assert summary["longest_run"]["activity_id"] == "123"
    assert comparison["distance_change_m"] == -5000.0
    assert [call[0] for call in fake_client.calls] == [
        "get_activities_by_date",
        "get_activities_by_date",
    ]


def test_recent_long_run_comparison_is_bounded_and_read_only(
    fake_client: FakeClient,
) -> None:
    result = server.garmin_compare_recent_long_runs("2030-05-12", limit=3)

    assert result["start_date"] == "2030-04-15"
    assert result["rule"].startswith("greatest supplied distance")
    assert result["latest_long_run"]["activity_id"] == "123"
    assert fake_client.calls == [
        (
            "get_activities_by_date",
            ("2030-04-15", "2030-05-12"),
            {"activitytype": "running", "sortorder": "asc"},
        )
    ]


@pytest.mark.parametrize(
    ("current", "previous"),
    [
        ("2030-04-09", "2030-04-02"),
        ("2030-04-08", "2030-03-25"),
        ("2030-4-08", "2030-04-01"),
    ],
)
def test_week_comparison_rejects_invalid_week_starts_before_garmin(
    fake_client: FakeClient, current: str, previous: str
) -> None:
    with pytest.raises(InvalidActivityRequestError, match="week"):
        server.garmin_compare_running_weeks(current, previous)
    assert fake_client.calls == []


@pytest.mark.parametrize("limit", [0, 5, True])
def test_recent_long_run_comparison_rejects_invalid_limit_before_garmin(
    fake_client: FakeClient, limit: int
) -> None:
    with pytest.raises(InvalidActivityRequestError, match="limit"):
        server.garmin_compare_recent_long_runs("2030-05-12", limit)
    assert fake_client.calls == []


def test_recent_long_run_comparison_rejects_date_underflow_before_garmin(
    fake_client: FakeClient,
) -> None:
    with pytest.raises(InvalidActivityRequestError, match="too early"):
        server.garmin_compare_recent_long_runs("0001-01-01", 4)
    assert fake_client.calls == []


def test_weekly_proposal_uses_only_four_normalized_read_operations(
    fake_client: FakeClient,
) -> None:
    result = server.garmin_weekly_running_proposal(
        "2030-04-01",
        server.ProposalConstraints(
            plan_start_date="2030-03-04",
            available_dates=["2030-04-02"],
            maximum_sessions=1,
        ),
    )

    assert result["proposal_only"] is True
    assert result["created"] is False
    assert result["scheduled"] is False
    assert result["proposed_sessions"] == []
    assert fake_client.calls == [
        (
            "get_activities_by_date",
            ("2030-03-04", "2030-03-31"),
            {"activitytype": "running", "sortorder": "asc"},
        ),
        ("get_hrv_data_range", ("2030-03-25", "2030-03-31"), {}),
        ("get_scheduled_workouts", (2030, 4), {}),
        ("get_heart_rate_zones", (), {}),
    ]


def test_running_heart_rate_zones_returns_compact_normalized_ranges(
    fake_client: FakeClient,
) -> None:
    result = server.garmin_running_heart_rate_zones()
    assert result["source_sport"] == "running"
    assert result["zones"][1] == {
        "zone": 2,
        "minimum_heart_rate_bpm": 120,
        "maximum_heart_rate_bpm": 139,
    }
    assert fake_client.calls == [("get_heart_rate_zones", (), {})]


@pytest.mark.parametrize(
    "arguments",
    [
        {
            "week_start": "2030-04-02",
            "constraints": {"plan_start_date": "2030-03-04"},
        },
        {
            "week_start": "2030-04-01T00:00:00",
            "constraints": {"plan_start_date": "2030-03-04"},
        },
        {
            "week_start": "2030-04-01",
            "constraints": {
                "plan_start_date": "2030-03-04",
                "maximum_sessions": "3",
            },
        },
        {
            "week_start": "2030-04-01",
            "constraints": {
                "plan_start_date": "2030-03-04",
                "desired_sessions": "4",
            },
        },
        {
            "week_start": "2030-04-01",
            "constraints": {
                "plan_start_date": "2030-03-04",
                "desired_sessions": 4,
                "maximum_sessions": 3,
            },
        },
        {
            "week_start": "2030-04-01",
            "constraints": {"plan_start_date": "2030-03-04", "unknown": True},
        },
        {
            "week_start": "2030-04-01",
            "constraints": {
                "plan_start_date": "2030-03-04",
                "available_dates": ["2030-04-08"],
            },
        },
        {
            "week_start": "2030-04-01",
            "constraints": {"plan_start_date": "2030-03-04"},
            "raw": {},
        },
    ],
)
def test_weekly_proposal_rejects_invalid_mcp_requests_before_garmin(
    fake_client: FakeClient, arguments: dict[str, object]
) -> None:
    async def call_tool() -> None:
        await server.mcp.call_tool("garmin_weekly_running_proposal", arguments)

    with pytest.raises(ToolError):
        anyio.run(call_tool)
    assert fake_client.calls == []


def test_garmin_workouts_returns_normalized_page(fake_client: FakeClient) -> None:
    assert server.garmin_workouts(start=2, limit=1, running_only=True) == {
        "start": 2,
        "limit": 1,
        "running_only": True,
        "source_count": 1,
        "count": 1,
        "items": [
            {
                "workout_id": "456",
                "name": "Easy Run",
                "sport_type": "running",
                "description": None,
                "estimated_duration_s": 1800.0,
                "estimated_distance_m": None,
            }
        ],
    }
    assert fake_client.calls == [
        (
            "connectapi",
            ("/workout-service/workouts",),
            {
                "params": {
                    "start": 3,
                    "limit": 1,
                    "myWorkoutsOnly": "true",
                    "sharedWorkoutsOnly": "false",
                    "includeAtp": "false",
                    "orderBy": "UPDATE_DATE",
                    "orderSeq": "DESC",
                    "sportTypeKey": "running",
                }
            },
        )
    ]


@pytest.mark.parametrize(
    "arguments",
    [
        {"start": 0, "limit": 1, "running_only": "true"},
        {"start": "0", "limit": 1, "running_only": False},
        {"start": 0, "limit": "1", "running_only": False},
    ],
)
def test_garmin_workouts_rejects_coerced_types_through_mcp(
    fake_client: FakeClient,
    arguments: dict[str, object],
) -> None:
    async def call_with_invalid_type() -> None:
        await server.mcp.call_tool("garmin_workouts", arguments)

    with pytest.raises(ToolError):
        anyio.run(call_with_invalid_type)

    assert fake_client.calls == []


def test_garmin_scheduled_workouts_returns_normalized_range(
    fake_client: FakeClient,
) -> None:
    assert server.garmin_scheduled_workouts("2026-05-24", "2026-05-24") == {
        "start_date": "2026-05-24",
        "end_date": "2026-05-24",
        "inclusive": True,
        "count": 1,
        "items": [
            {
                "scheduled_workout_id": "789",
                "scheduled_date": "2026-05-24",
                "workout_id": "456",
                "name": "Easy Run",
                "sport_type": "running",
                "description": None,
                "estimated_duration_s": None,
                "estimated_distance_m": None,
            }
        ],
    }
    assert fake_client.calls == [("get_scheduled_workouts", (2026, 5), {})]


def synthetic_creation_definition() -> dict[str, object]:
    return {
        "name": "Synthetic Creation Fixture",
        "steps": [
            {
                "step_type": "run",
                "duration": {"duration_type": "time", "duration_s": 600},
            }
        ],
    }


def test_running_workout_creation_defaults_to_no_write(
    fake_client: FakeClient,
) -> None:
    assert server.garmin_create_running_workout(synthetic_creation_definition()) == {
        "created": False,
        "workout_id": None,
        "name": "Synthetic Creation Fixture",
        "sport_type": "running",
        "total_duration_s": 600.0,
        "total_distance_m": None,
        "scheduled": False,
        "message": (
            "Not created; preview the validated workout, then call again with "
            "confirmed=true to create exactly one unscheduled workout."
        ),
    }
    assert fake_client.calls == []


@pytest.mark.parametrize("arguments", [{}, {"confirmed": False}])
def test_unconfirmed_running_workout_creation_does_not_construct_client_through_mcp(
    monkeypatch: pytest.MonkeyPatch, arguments: dict[str, object]
) -> None:
    client_constructions = 0

    def forbidden_client() -> object:
        nonlocal client_constructions
        client_constructions += 1
        raise AssertionError("Garmin client must not be constructed")

    monkeypatch.setattr(server, "_client", forbidden_client)

    async def call_unconfirmed() -> object:
        return await server.mcp.call_tool(
            "garmin_create_running_workout",
            {"definition": synthetic_creation_definition(), **arguments},
        )

    _, result = anyio.run(call_unconfirmed)

    assert result["created"] is False
    assert client_constructions == 0


def test_confirmed_running_workout_creation_uploads_once(
    fake_client: FakeClient,
) -> None:
    assert server.garmin_create_running_workout(
        synthetic_creation_definition(), confirmed=True
    ) == {
        "created": True,
        "workout_id": "456",
        "name": "Synthetic Creation Fixture",
        "sport_type": "running",
        "total_duration_s": 600.0,
        "total_distance_m": None,
        "scheduled": False,
        "message": "Workout created in Garmin Connect but not scheduled.",
    }
    assert [call[0] for call in fake_client.calls] == ["upload_workout"]


def test_confirmed_running_workout_creation_uses_fake_client_through_mcp(
    fake_client: FakeClient,
) -> None:
    async def call_confirmed() -> object:
        return await server.mcp.call_tool(
            "garmin_create_running_workout",
            {
                "definition": synthetic_creation_definition(),
                "confirmed": True,
            },
        )

    _, result = anyio.run(call_confirmed)

    assert result == {
        "created": True,
        "workout_id": "456",
        "name": "Synthetic Creation Fixture",
        "sport_type": "running",
        "total_duration_s": 600.0,
        "total_distance_m": None,
        "scheduled": False,
        "message": "Workout created in Garmin Connect but not scheduled.",
    }
    assert [call[0] for call in fake_client.calls] == ["upload_workout"]


@pytest.mark.parametrize(
    "definition",
    [
        {"name": "Synthetic Invalid", "steps": []},
        {"name": "Synthetic Invalid", "steps": [], "unknown": True},
        {
            "name": "Synthetic Invalid",
            "sport_type": "cycling",
            "steps": [
                {
                    "step_type": "run",
                    "duration": {"duration_type": "time", "duration_s": 60},
                }
            ],
        },
        {
            "name": "Synthetic Invalid",
            "steps": [
                {
                    "step_type": "unknown",
                    "duration": {"duration_type": "time", "duration_s": 60},
                }
            ],
        },
        {
            "name": "Synthetic Invalid",
            "steps": [
                {
                    "step_type": "run",
                    "duration": {"duration_type": "time", "duration_s": "60"},
                }
            ],
        },
        {
            "name": "Synthetic Invalid",
            "steps": [
                {
                    "step_type": "run",
                    "duration": {"duration_type": "open", "distance_m": 100},
                }
            ],
        },
        {
            "name": "Synthetic Invalid",
            "steps": [
                {
                    "step_type": "run",
                    "duration": {"duration_type": "time", "duration_s": 60},
                    "target": {
                        "target_type": "heart_rate_range",
                        "minimum_heart_rate_bpm": 160,
                        "maximum_heart_rate_bpm": 150,
                    },
                }
            ],
        },
        {
            "name": "Synthetic Invalid",
            "steps": [{"step_type": "repeat", "repeat_count": 2, "steps": []}],
        },
        {
            "name": "Synthetic Invalid",
            "steps": [
                {
                    "step_type": "repeat",
                    "repeat_count": 50,
                    "steps": [
                        {
                            "step_type": "run",
                            "duration": {
                                "duration_type": "time",
                                "duration_s": 60,
                            },
                        },
                        {
                            "step_type": "recovery",
                            "duration": {
                                "duration_type": "time",
                                "duration_s": 60,
                            },
                        },
                    ],
                },
                {
                    "step_type": "cooldown",
                    "duration": {"duration_type": "time", "duration_s": 60},
                },
            ],
        },
    ],
)
def test_all_builder_validation_categories_fail_before_client_construction(
    monkeypatch: pytest.MonkeyPatch, definition: dict[str, object]
) -> None:
    client_constructions = 0

    def forbidden_client() -> object:
        nonlocal client_constructions
        client_constructions += 1
        raise AssertionError("Garmin client must not be constructed")

    monkeypatch.setattr(server, "_client", forbidden_client)

    async def call_invalid() -> None:
        await server.mcp.call_tool(
            "garmin_create_running_workout",
            {"definition": definition, "confirmed": True},
        )

    with pytest.raises(ToolError):
        anyio.run(call_invalid)

    assert client_constructions == 0


@pytest.mark.parametrize("confirmed", ["true", 1, 0, None])
def test_running_workout_creation_requires_strict_boolean_confirmation_through_mcp(
    fake_client: FakeClient, confirmed: object
) -> None:
    async def call_with_invalid_confirmation() -> None:
        await server.mcp.call_tool(
            "garmin_create_running_workout",
            {"definition": synthetic_creation_definition(), "confirmed": confirmed},
        )

    with pytest.raises(ToolError):
        anyio.run(call_with_invalid_confirmation)

    assert fake_client.calls == []


@pytest.mark.parametrize(
    "definition",
    [
        {"workoutName": "Unsafe payload", "workoutSegments": []},
        [synthetic_creation_definition(), synthetic_creation_definition()],
    ],
)
def test_running_workout_creation_rejects_arbitrary_or_bulk_payloads_before_client(
    fake_client: FakeClient, definition: object
) -> None:
    async def call_with_unsafe_definition() -> None:
        await server.mcp.call_tool(
            "garmin_create_running_workout",
            {
                "definition": definition,
                "confirmed": True,
            },
        )

    with pytest.raises(ToolError):
        anyio.run(call_with_unsafe_definition)

    assert fake_client.calls == []


def synthetic_combined_definition() -> dict[str, object]:
    return {
        "name": "MCP TEST M10 Synthetic",
        "description": "Offline synthetic fixture",
        "steps": [
            {
                "step_type": "warmup",
                "duration": {"duration_type": "time", "duration_s": 120},
            },
            {
                "step_type": "run",
                "duration": {"duration_type": "time", "duration_s": 180},
                "target": {
                    "target_type": "heart_rate_range",
                    "minimum_heart_rate_bpm": 120,
                    "maximum_heart_rate_bpm": 140,
                },
            },
            {
                "step_type": "cooldown",
                "duration": {"duration_type": "time", "duration_s": 120},
            },
        ],
    }


@pytest.mark.parametrize(
    ("tool_name", "extra"),
    [
        ("garmin_preview_create_and_schedule_running_workout", {}),
        ("garmin_create_and_schedule_running_workout", {}),
        ("garmin_create_and_schedule_running_workout", {"confirmed": False}),
    ],
)
def test_combined_preview_and_unconfirmed_are_fully_offline(
    monkeypatch: pytest.MonkeyPatch, tool_name: str, extra: dict[str, object]
) -> None:
    constructions = 0

    def forbidden_client() -> object:
        nonlocal constructions
        constructions += 1
        raise AssertionError("Garmin client must not be constructed")

    monkeypatch.setattr(server, "_client", forbidden_client)

    async def call_tool() -> object:
        return await server.mcp.call_tool(
            tool_name,
            {
                "definition": synthetic_combined_definition(),
                "scheduled_date": "2030-06-15",
                **extra,
            },
        )

    _, result = anyio.run(call_tool)

    assert result["created"] is False
    assert result["scheduled"] is False
    assert result["preview_only"] is True
    assert result["scheduled_date"] == "2030-06-15"
    assert result["aggregates"]["total_duration_s"] == 420.0
    assert [step["order"] for step in result["expanded_steps"]] == [1, 2, 3]
    assert constructions == 0


@pytest.mark.parametrize(
    "tool_name",
    [
        "garmin_preview_create_and_schedule_running_workout",
        "garmin_create_and_schedule_running_workout",
    ],
)
def test_combined_tool_schemas_forbid_unknown_fields(tool_name: str) -> None:
    tool = server.mcp._tool_manager.get_tool(tool_name)

    assert tool is not None
    assert tool.parameters["additionalProperties"] is False


@pytest.mark.parametrize(
    "arguments",
    [
        {
            "definition": [synthetic_combined_definition()],
            "scheduled_date": "2030-06-15",
        },
        {"definition": {"workoutName": "Unsafe"}, "scheduled_date": "2030-06-15"},
        {
            "definition": synthetic_combined_definition(),
            "scheduled_date": ["2030-06-15"],
        },
        {"definition": synthetic_combined_definition(), "scheduled_date": "2030-6-15"},
        {
            "definition": synthetic_combined_definition(),
            "scheduled_date": "2030-06-15T00:00:00Z",
        },
        {
            "definition": synthetic_combined_definition(),
            "scheduled_date": "2030-06-15",
            "confirmed": "true",
        },
        {
            "definition": synthetic_combined_definition(),
            "scheduled_date": "2030-06-15",
            "confirmed": 1,
        },
        {
            "definition": synthetic_combined_definition(),
            "scheduled_date": "2030-06-15",
            "workout_id": "456",
        },
        {
            "definition": synthetic_combined_definition(),
            "scheduled_date": "2030-06-15",
            "url": "https://private.invalid",
        },
    ],
)
def test_combined_rejects_unsafe_mcp_input_before_client(
    fake_client: FakeClient, arguments: dict[str, object]
) -> None:
    async def call_invalid() -> None:
        await server.mcp.call_tool(
            "garmin_create_and_schedule_running_workout", arguments
        )

    with pytest.raises(ToolError):
        anyio.run(call_invalid)

    assert fake_client.calls == []


def test_confirmed_combined_mcp_call_uploads_once_and_schedules_returned_id(
    fake_client: FakeClient,
) -> None:
    async def call_confirmed() -> object:
        return await server.mcp.call_tool(
            "garmin_create_and_schedule_running_workout",
            {
                "definition": synthetic_combined_definition(),
                "scheduled_date": "2026-05-25",
                "confirmed": True,
            },
        )

    _, result = anyio.run(call_confirmed)

    assert result == {
        "created": True,
        "workout_id": "456",
        "scheduled": True,
        "already_scheduled": False,
        "scheduled_workout_id": "789",
        "scheduled_date": "2026-05-25",
        "name": "MCP TEST M10 Synthetic",
        "sport_type": "running",
        "total_duration_s": 420.0,
        "total_distance_m": None,
        "partial_failure": False,
        "message": (
            "Exactly one new workout was created and scheduled in Garmin Connect."
        ),
    }
    assert [call[0] for call in fake_client.calls] == [
        "upload_workout",
        "get_scheduled_workouts",
        "schedule_workout",
    ]
    assert fake_client.calls[-1][1][0] == "456"


def test_schedule_preview_is_offline_and_compact(fake_client: FakeClient) -> None:
    assert server.garmin_preview_workout_schedule("456", "2026-05-25") == {
        "scheduled": False,
        "already_scheduled": False,
        "scheduled_workout_id": None,
        "workout_id": "456",
        "scheduled_date": "2026-05-25",
        "message": (
            "Preview only: no Garmin calendar change occurred. A confirmed "
            "schedule may later be synchronized by Garmin to connected devices; "
            "this server will not call a device-push method."
        ),
    }
    assert fake_client.calls == []


@pytest.mark.parametrize(
    "tool_name",
    [
        "garmin_preview_workout_schedule",
        "garmin_schedule_existing_workout",
        "garmin_unschedule_existing_workout",
    ],
)
def test_milestone_9_tool_schemas_forbid_unknown_fields(tool_name: str) -> None:
    tool = server.mcp._tool_manager.get_tool(tool_name)

    assert tool is not None
    assert tool.parameters["additionalProperties"] is False


@pytest.mark.parametrize(
    ("tool_name", "extra_arguments"),
    [
        ("garmin_preview_workout_schedule", {}),
        ("garmin_schedule_existing_workout", {}),
        ("garmin_schedule_existing_workout", {"confirmed": False}),
    ],
)
def test_schedule_preview_and_unconfirmed_call_do_not_construct_client_through_mcp(
    monkeypatch: pytest.MonkeyPatch,
    tool_name: str,
    extra_arguments: dict[str, object],
) -> None:
    constructions = 0

    def forbidden_client() -> object:
        nonlocal constructions
        constructions += 1
        raise AssertionError("Garmin client must not be constructed")

    monkeypatch.setattr(server, "_client", forbidden_client)

    async def call_tool() -> object:
        return await server.mcp.call_tool(
            tool_name,
            {
                "workout_id": "456",
                "scheduled_date": "2026-05-25",
                **extra_arguments,
            },
        )

    _, result = anyio.run(call_tool)

    assert result["scheduled"] is False
    assert constructions == 0


@pytest.mark.parametrize(
    "arguments",
    [
        {"workout_id": 456, "scheduled_date": "2026-05-25"},
        {"workout_id": ["456"], "scheduled_date": "2026-05-25"},
        {"workout_id": {"id": "456"}, "scheduled_date": "2026-05-25"},
        {"workout_id": "0", "scheduled_date": "2026-05-25"},
        {"workout_id": "0456", "scheduled_date": "2026-05-25"},
        {"workout_id": "456 ", "scheduled_date": "2026-05-25"},
        {
            "workout_id": "https://private.invalid/456",
            "scheduled_date": "2026-05-25",
        },
        {"workout_id": "456", "scheduled_date": ["2026-05-25"]},
        {"workout_id": "456", "scheduled_date": "2026-5-25"},
        {"workout_id": "456", "scheduled_date": "2026-05-25T00:00:00Z"},
        {
            "workout_id": "456",
            "scheduled_date": "2026-05-25",
            "confirmed": "true",
        },
        {
            "workout_id": "456",
            "scheduled_date": "2026-05-25",
            "confirmed": 1,
        },
        {
            "workout_id": "456",
            "scheduled_date": "2026-05-25",
            "confirmed": True,
            "unknown": {"garmin": "json"},
        },
    ],
)
def test_schedule_rejects_unsafe_inputs_before_client_through_mcp(
    fake_client: FakeClient, arguments: dict[str, object]
) -> None:
    async def call_invalid() -> None:
        await server.mcp.call_tool("garmin_schedule_existing_workout", arguments)

    with pytest.raises(ToolError):
        anyio.run(call_invalid)

    assert fake_client.calls == []


def test_confirmed_schedule_uses_duplicate_read_then_one_schedule_call_through_mcp(
    fake_client: FakeClient,
) -> None:
    async def call_confirmed() -> object:
        return await server.mcp.call_tool(
            "garmin_schedule_existing_workout",
            {
                "workout_id": "456",
                "scheduled_date": "2026-05-25",
                "confirmed": True,
            },
        )

    _, result = anyio.run(call_confirmed)

    assert result == {
        "scheduled": True,
        "already_scheduled": False,
        "scheduled_workout_id": "789",
        "workout_id": "456",
        "scheduled_date": "2026-05-25",
        "message": "Exactly one existing workout was scheduled in Garmin Connect.",
    }
    assert fake_client.calls == [
        ("get_scheduled_workouts", (2026, 5), {}),
        ("schedule_workout", ("456", "2026-05-25"), {}),
    ]


def test_confirmed_exact_duplicate_makes_no_schedule_call_through_mcp(
    fake_client: FakeClient,
) -> None:
    async def call_duplicate() -> object:
        return await server.mcp.call_tool(
            "garmin_schedule_existing_workout",
            {
                "workout_id": "456",
                "scheduled_date": "2026-05-24",
                "confirmed": True,
            },
        )

    _, result = anyio.run(call_duplicate)

    assert result["scheduled"] is False
    assert result["already_scheduled"] is True
    assert result["scheduled_workout_id"] == "789"
    assert fake_client.calls == [("get_scheduled_workouts", (2026, 5), {})]


def test_unschedule_default_previews_exact_assignment_without_write_through_mcp(
    fake_client: FakeClient,
) -> None:
    async def call_preview() -> object:
        return await server.mcp.call_tool(
            "garmin_unschedule_existing_workout",
            {"scheduled_workout_id": "789"},
        )

    _, result = anyio.run(call_preview)

    assert result == {
        "unscheduled": False,
        "scheduled_workout_id": "789",
        "workout_id": "456",
        "scheduled_date": "2026-05-24",
        "workout_deleted": False,
        "message": (
            "Preview only: no calendar assignment was removed. Call again with "
            "confirmed=true only after reviewing this exact assignment; the "
            "underlying workout template will not be deleted."
        ),
    }
    assert fake_client.calls == [("get_scheduled_workout_by_id", ("789",), {})]


def test_confirmed_unschedule_reads_then_unschedules_once_through_mcp(
    fake_client: FakeClient,
) -> None:
    async def call_confirmed() -> object:
        return await server.mcp.call_tool(
            "garmin_unschedule_existing_workout",
            {"scheduled_workout_id": "789", "confirmed": True},
        )

    _, result = anyio.run(call_confirmed)

    assert result == {
        "unscheduled": True,
        "scheduled_workout_id": "789",
        "workout_id": "456",
        "scheduled_date": "2026-05-24",
        "workout_deleted": False,
        "message": (
            "Only the Garmin calendar assignment was removed; the workout "
            "template was not deleted."
        ),
    }
    assert fake_client.calls == [
        ("get_scheduled_workout_by_id", ("789",), {}),
        ("unschedule_workout", ("789",), {}),
    ]


@pytest.mark.parametrize(
    "arguments",
    [
        {"scheduled_workout_id": 789},
        {"scheduled_workout_id": ["789"]},
        {"scheduled_workout_id": "0789"},
        {"scheduled_workout_id": "789", "confirmed": "true"},
        {"scheduled_workout_id": "789", "confirmed": 1},
        {"scheduled_workout_id": "789", "confirmed": True, "unknown": True},
    ],
)
def test_unschedule_rejects_unsafe_inputs_before_client_through_mcp(
    fake_client: FakeClient, arguments: dict[str, object]
) -> None:
    async def call_invalid() -> None:
        await server.mcp.call_tool("garmin_unschedule_existing_workout", arguments)

    with pytest.raises(ToolError):
        anyio.run(call_invalid)

    assert fake_client.calls == []


def test_garmin_schedule_workout_returns_summary(fake_client: FakeClient) -> None:
    assert server.garmin_schedule_workout("456", "2026-05-24") == {
        "scheduled_workout_id": 789,
        "date": "2026-05-24",
        "workout_id": "456",
        "name": "Easy Run",
        "sport_type": "running",
        "estimated_duration_secs": None,
        "scheduled": True,
    }
    assert fake_client.calls == [("schedule_workout", ("456", "2026-05-24"), {})]


def test_garmin_create_scheduled_workout_uploads_then_schedules(
    fake_client: FakeClient,
) -> None:
    workout = {"workoutName": "Easy Run"}

    assert server.garmin_create_scheduled_workout(workout, "2026-05-24") == {
        "scheduled_workout_id": 789,
        "date": "2026-05-24",
        "workout_id": 456,
        "name": "Easy Run",
        "sport_type": "running",
        "estimated_duration_secs": None,
        "uploaded_workout_id": 456,
        "scheduled": True,
    }
    assert fake_client.calls == [
        ("upload_workout", (workout,), {}),
        ("schedule_workout", (456, "2026-05-24"), {}),
    ]


def test_garmin_create_scheduled_workout_requires_uploaded_workout_id(
    monkeypatch: pytest.MonkeyPatch, fake_client: FakeClient
) -> None:
    monkeypatch.setattr(fake_client, "upload_workout", lambda workout: {"ok": True})

    with pytest.raises(ValueError, match="workout ID"):
        server.garmin_create_scheduled_workout({"workoutName": "No ID"}, "2026-05-24")


def test_garmin_unschedule_workout_returns_confirmation(
    fake_client: FakeClient,
) -> None:
    assert server.garmin_unschedule_workout("789") == {
        "unscheduled": True,
        "scheduled_workout_id": "789",
    }
    assert fake_client.calls == [("unschedule_workout", ("789",), {})]


def test_login_once_checks_client_without_data_call(fake_client: FakeClient) -> None:
    assert server.login_once() == {"ok": True}
    assert fake_client.calls == []


def test_main_login_uses_login_once_and_reports_token_dir(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(server, "login_once", lambda: {"ok": True})
    monkeypatch.setattr(server, "_token_dir", lambda: "/tmp/garmin-tokens")

    server.main(["login"])

    assert capsys.readouterr().out == (
        "Garmin login ok. Tokens stored in /tmp/garmin-tokens.\n"
    )


def test_main_rejects_unknown_command() -> None:
    with pytest.raises(SystemExit, match=r"garminconnect-mcp \[serve\|login\]"):
        server.main(["unknown"])


def test_milestone_12_preview_and_unconfirmed_mcp_boundary(
    monkeypatch: pytest.MonkeyPatch, fake_client: FakeClient
) -> None:
    monkeypatch.setattr(
        server,
        "_weekly_approval_store",
        server.ApprovalStore(token_factory=lambda: "D" * 43),
    )
    reviewed = server.garmin_preview_weekly_running_plan(
        "2030-04-01",
        server.ProposalConstraints(
            plan_start_date="2030-03-04",
            desired_sessions=1,
            maximum_sessions=1,
        ),
    )
    assert reviewed["preview_only"] is True
    assert reviewed["created"] is False
    assert reviewed["scheduled"] is False
    assert reviewed["approval_token"] == "D" * 43
    assert [call[0] for call in fake_client.calls] == [
        "get_activities_by_date",
        "get_hrv_data_range",
        "get_scheduled_workouts",
        "get_heart_rate_zones",
    ]
    fake_client.calls.clear()

    result = server.garmin_schedule_weekly_running_plan(
        reviewed["approval_token"],
        reviewed["proposal_fingerprint"],
        confirmed=False,
    )
    assert result["preview_only"] is True
    assert result["created"] is False
    assert result["scheduled"] is False
    assert fake_client.calls == []


@pytest.mark.parametrize(
    "tool_name",
    [
        "garmin_preview_weekly_running_plan",
        "garmin_schedule_weekly_running_plan",
    ],
)
def test_milestone_12_tool_schemas_forbid_unknown_fields(tool_name: str) -> None:
    tool = server.mcp._tool_manager.get_tool(tool_name)
    assert tool is not None
    assert tool.parameters["additionalProperties"] is False


@pytest.mark.parametrize(
    "arguments",
    [
        {
            "approval_token": ["D" * 43],
            "proposal_fingerprint": "sha256:" + "0" * 64,
        },
        {
            "approval_token": "https://invalid.example",
            "proposal_fingerprint": "sha256:" + "0" * 64,
        },
        {
            "approval_token": "D" * 43,
            "proposal_fingerprint": {"raw": "payload"},
        },
        {
            "approval_token": "D" * 43,
            "proposal_fingerprint": "sha256:" + "0" * 64,
            "confirmed": "true",
        },
        {
            "approval_token": "D" * 43,
            "proposal_fingerprint": "sha256:" + "0" * 64,
            "workout_id": "123",
        },
        {
            "approval_token": "D" * 43,
            "proposal_fingerprint": "sha256:" + "0" * 64,
            "scheduled_workout_id": "456",
        },
        {
            "approval_token": "D" * 43,
            "proposal_fingerprint": "sha256:" + "0" * 64,
            "proposal": [{"rawGarminJson": True}],
        },
    ],
)
def test_milestone_12_schedule_rejects_unsafe_mcp_inputs(
    fake_client: FakeClient, arguments: dict[str, object]
) -> None:
    async def call_tool() -> None:
        await server.mcp.call_tool("garmin_schedule_weekly_running_plan", arguments)

    with pytest.raises(ToolError):
        anyio.run(call_tool)
    assert fake_client.calls == []


def test_milestone_12_synthetic_mcp_outcome_routes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[object, ...]] = []

    class SyntheticWeeklyService:
        def preview(self, week_start: str, constraints: object) -> dict[str, object]:
            calls.append(("preview", week_start, constraints))
            return {
                "week_start": week_start,
                "preview_only": True,
                "created": False,
                "scheduled": False,
            }

        def schedule(
            self,
            approval_token: str,
            proposal_fingerprint: str,
            *,
            confirmed: bool,
        ) -> dict[str, object]:
            calls.append(("schedule", approval_token, proposal_fingerprint, confirmed))
            states = {
                "U": (False, False),
                "S": (False, False),
                "P": (True, False),
                "X": (True, True),
            }
            partial_failure, uncertain = states[approval_token[0]]
            return {
                "week_start": "2030-04-01",
                "preview_only": not confirmed,
                "partial_failure": partial_failure,
                "uncertain": uncertain,
            }

    synthetic = SyntheticWeeklyService()
    monkeypatch.setattr(server, "_weekly_scheduling_service", lambda: synthetic)

    async def call_all() -> list[dict[str, object]]:
        results: list[dict[str, object]] = []
        _, result = await server.mcp.call_tool(
            "garmin_preview_weekly_running_plan",
            {
                "week_start": "2030-04-01",
                "constraints": {"plan_start_date": "2030-03-04"},
            },
        )
        results.append(result)
        for prefix, confirmed in [("U", False), ("S", True), ("P", True), ("X", True)]:
            _, result = await server.mcp.call_tool(
                "garmin_schedule_weekly_running_plan",
                {
                    "approval_token": prefix * 43,
                    "proposal_fingerprint": "sha256:" + prefix.casefold() * 64,
                    "confirmed": confirmed,
                },
            )
            results.append(result)
        return results

    results = anyio.run(call_all)
    assert results[0]["preview_only"] is True
    assert results[1]["preview_only"] is True
    assert results[2]["partial_failure"] is False
    assert results[3]["partial_failure"] is True
    assert results[3]["uncertain"] is False
    assert results[4]["uncertain"] is True
    assert [item[0] for item in calls] == [
        "preview",
        "schedule",
        "schedule",
        "schedule",
        "schedule",
    ]
