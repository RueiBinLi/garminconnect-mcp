from __future__ import annotations

import pytest

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
                "estimatedDurationInSecs": 1800,
            }
        ]

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


def test_garmin_workouts_returns_summary(fake_client: FakeClient) -> None:
    assert server.garmin_workouts(start=2, limit=1) == {
        "count": 1,
        "items": [
            {
                "workout_id": 456,
                "name": "Easy Run",
                "sport_type": "running",
                "estimated_duration_secs": 1800,
            }
        ],
    }
    assert fake_client.calls == [("get_workouts", (2, 1), {})]


def test_garmin_scheduled_workouts_returns_summary(fake_client: FakeClient) -> None:
    assert server.garmin_scheduled_workouts(2026, 5) == {
        "count": 1,
        "items": [
            {
                "scheduled_workout_id": 789,
                "date": "2026-05-24",
                "workout_id": 456,
                "name": "Easy Run",
                "sport_type": "running",
                "estimated_duration_secs": None,
            }
        ],
    }
    assert fake_client.calls == [("get_scheduled_workouts", (2026, 5), {})]


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
