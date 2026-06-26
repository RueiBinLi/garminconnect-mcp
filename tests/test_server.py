from __future__ import annotations

import pytest

from garminconnect_mcp import server


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
        return self._record("get_stats", cdate)

    def get_heart_rates(self, cdate: str) -> dict[str, object]:
        return self._record("get_heart_rates", cdate)

    def get_sleep_data(self, cdate: str) -> dict[str, object]:
        return self._record("get_sleep_data", cdate)

    def get_hrv_data(self, cdate: str) -> dict[str, object]:
        return self._record("get_hrv_data", cdate)

    def get_body_battery(self, startdate: str) -> list[dict[str, object]]:
        self.calls.append(("get_body_battery", (startdate,), {}))
        return [{"method": "get_body_battery", "args": (startdate,)}]

    def get_stress_data(self, cdate: str) -> dict[str, object]:
        return self._record("get_stress_data", cdate)

    def get_activities(self, start: int = 0, limit: int = 20) -> list[dict[str, int]]:
        self.calls.append(("get_activities", (start, limit), {}))
        return [{"activityId": 123}]

    def get_activity_details(self, activity_id: str) -> dict[str, object]:
        return self._record("get_activity_details", activity_id)

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
    result = server._call_first(("missing_method", "get_stats"), "2026-05-21")

    assert result == {
        "method": "get_stats",
        "args": ("2026-05-21",),
        "kwargs": {},
    }
    assert fake_client.calls == [("get_stats", ("2026-05-21",), {})]


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

    assert server.garmin_daily_stats()["args"] == ("2026-05-21",)
    assert server.garmin_heart_rate()["args"] == ("2026-05-21",)
    assert server.garmin_sleep()["args"] == ("2026-05-21",)
    assert server.garmin_hrv()["args"] == ("2026-05-21",)
    assert server.garmin_body_battery()[0]["args"] == ("2026-05-21",)
    assert server.garmin_stress()["args"] == ("2026-05-21",)

    assert [call[0] for call in fake_client.calls] == [
        "get_stats",
        "get_heart_rates",
        "get_sleep_data",
        "get_hrv_data",
        "get_body_battery",
        "get_stress_data",
    ]


def test_tools_pass_explicit_arguments(fake_client: FakeClient) -> None:
    assert server.garmin_daily_stats("2026-05-20")["args"] == ("2026-05-20",)
    assert server.garmin_recent_activities(start=5, limit=2) == [{"activityId": 123}]
    assert server.garmin_activity("987")["args"] == ("987",)

    assert fake_client.calls == [
        ("get_stats", ("2026-05-20",), {}),
        ("get_activities", (5, 2), {}),
        ("get_activity_details", ("987",), {}),
    ]


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
