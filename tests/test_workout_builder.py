from __future__ import annotations

import math
from typing import Any

import anyio
import pytest
from mcp.server.fastmcp.exceptions import ToolError
from pydantic import ValidationError

from garminconnect_mcp import server
from garminconnect_mcp.workout_builder import (
    MAX_DESCRIPTION_LENGTH,
    MAX_EXPANDED_STEP_COUNT,
    MAX_NAME_LENGTH,
    MAX_REPEAT_COUNT,
    MAX_STEP_DISTANCE_M,
    MAX_STEP_DURATION_S,
    MAX_TOTAL_DISTANCE_M,
    MAX_TOTAL_DURATION_S,
    WorkoutDefinition,
    aggregate_workout,
    preview_running_workout,
    serialize_running_workout,
)


def time_duration(duration_s: object = 300) -> dict[str, object]:
    return {"duration_type": "time", "duration_s": duration_s}


def distance_duration(distance_m: object = 400) -> dict[str, object]:
    return {"duration_type": "distance", "distance_m": distance_m}


def executable(
    step_type: str = "run",
    *,
    duration: dict[str, object] | None = None,
    target: dict[str, object] | None = None,
) -> dict[str, object]:
    result: dict[str, object] = {
        "step_type": step_type,
        "duration": duration or time_duration(),
    }
    if target is not None:
        result["target"] = target
    return result


def definition(steps: list[dict[str, object]]) -> dict[str, object]:
    return {
        "sport_type": "running",
        "name": "Synthetic Builder Fixture",
        "description": "Offline synthetic definition",
        "steps": steps,
    }


def validate(raw: dict[str, object]) -> WorkoutDefinition:
    return WorkoutDefinition.model_validate(raw, strict=True)


@pytest.mark.parametrize("step_type", ["warmup", "run", "recovery", "cooldown"])
@pytest.mark.parametrize(
    "duration",
    [time_duration(90), distance_duration(500), {"duration_type": "open"}],
)
def test_each_executable_step_and_duration_type_is_supported(
    step_type: str, duration: dict[str, object]
) -> None:
    workout = validate(definition([executable(step_type, duration=duration)]))

    preview = preview_running_workout(workout)

    assert preview["expanded_steps"][0]["step_type"] == step_type
    assert preview["expanded_steps"][0]["duration"] == {
        key: float(value) if key != "duration_type" else value
        for key, value in duration.items()
    }


@pytest.mark.parametrize(
    ("target", "expected_wire_type", "expected_values"),
    [
        ({"target_type": "none"}, "no.target", (None, None)),
        (
            {
                "target_type": "heart_rate_range",
                "minimum_heart_rate_bpm": 140,
                "maximum_heart_rate_bpm": 155,
            },
            "heart.rate.zone",
            (140, 155),
        ),
        (
            {
                "target_type": "pace_range",
                "minimum_pace_s_per_km": 300,
                "maximum_pace_s_per_km": 330,
            },
            "pace.zone",
            (round(1000 / 330, 8), round(1000 / 300, 8)),
        ),
    ],
)
def test_verified_targets_serialize_with_step_level_bounds(
    target: dict[str, object],
    expected_wire_type: str,
    expected_values: tuple[float | None, float | None],
) -> None:
    workout = validate(definition([executable(target=target)]))

    step = serialize_running_workout(workout)["workoutSegments"][0]["workoutSteps"][0]

    assert step["targetType"]["workoutTargetTypeKey"] == expected_wire_type
    assert step.get("targetValueOne") == expected_values[0]
    assert step.get("targetValueTwo") == expected_values[1]
    assert "targetValueOne" not in step["targetType"]
    assert "targetValueTwo" not in step["targetType"]


def test_mixed_repeat_workout_has_readable_expanded_order_and_totals() -> None:
    workout = validate(
        definition(
            [
                executable("warmup", duration=time_duration(600)),
                {
                    "step_type": "repeat",
                    "repeat_count": 3,
                    "steps": [
                        executable("run", duration=distance_duration(400)),
                        executable("recovery", duration=time_duration(60)),
                    ],
                },
                executable("cooldown", duration={"duration_type": "open"}),
            ]
        )
    )

    preview = preview_running_workout(workout)

    assert [step["step_type"] for step in preview["expanded_steps"]] == [
        "warmup",
        "run",
        "recovery",
        "run",
        "recovery",
        "run",
        "recovery",
        "cooldown",
    ]
    assert [step["order"] for step in preview["expanded_steps"]] == list(range(1, 9))
    assert preview["aggregates"] == {
        "expanded_step_count": 8,
        "known_duration_s": 780.0,
        "total_duration_s": None,
        "duration_total_complete": False,
        "known_distance_m": 1200.0,
        "total_distance_m": None,
        "distance_total_complete": False,
    }


def test_complete_time_and_distance_totals_are_explicit() -> None:
    timed = validate(definition([executable(duration=time_duration(300))]))
    distanced = validate(definition([executable(duration=distance_duration(1000))]))

    assert aggregate_workout(timed) == {
        "expanded_step_count": 1,
        "known_duration_s": 300.0,
        "total_duration_s": 300.0,
        "duration_total_complete": True,
        "known_distance_m": 0.0,
        "total_distance_m": None,
        "distance_total_complete": False,
    }
    assert aggregate_workout(distanced) == {
        "expanded_step_count": 1,
        "known_duration_s": 0.0,
        "total_duration_s": None,
        "duration_total_complete": False,
        "known_distance_m": 1000.0,
        "total_distance_m": 1000.0,
        "distance_total_complete": True,
    }


def test_two_repeat_levels_are_supported_and_three_are_rejected() -> None:
    inner: dict[str, object] = {
        "step_type": "repeat",
        "repeat_count": 2,
        "steps": [executable()],
    }
    valid = validate(
        definition([{"step_type": "repeat", "repeat_count": 2, "steps": [inner]}])
    )
    assert aggregate_workout(valid)["expanded_step_count"] == 4

    too_deep = {
        "step_type": "repeat",
        "repeat_count": 2,
        "steps": [inner],
    }
    with pytest.raises(ValidationError, match="nesting depth"):
        validate(
            definition(
                [
                    {
                        "step_type": "repeat",
                        "repeat_count": 2,
                        "steps": [too_deep],
                    }
                ]
            )
        )


def test_serialization_is_deterministic_and_uses_global_structural_order() -> None:
    workout = validate(
        definition(
            [
                executable("warmup"),
                {
                    "step_type": "repeat",
                    "repeat_count": 2,
                    "steps": [executable("run"), executable("recovery")],
                },
                executable("cooldown"),
            ]
        )
    )

    first = serialize_running_workout(workout)
    second = serialize_running_workout(workout)
    top = first["workoutSegments"][0]["workoutSteps"]

    assert first == second
    assert isinstance(first["estimatedDurationInSecs"], int)
    assert [step["stepOrder"] for step in top] == [1, 2, 5]
    assert [step["stepOrder"] for step in top[1]["workoutSteps"]] == [3, 4]
    assert top[1]["type"] == "RepeatGroupDTO"
    assert top[1]["endCondition"]["conditionTypeKey"] == "iterations"


def test_open_duration_uses_lap_button_without_a_value() -> None:
    workout = validate(
        definition([executable("cooldown", duration={"duration_type": "open"})])
    )

    step = serialize_running_workout(workout)["workoutSegments"][0]["workoutSteps"][0]

    assert step["endCondition"]["conditionTypeKey"] == "lap.button"
    assert "endConditionValue" not in step


def test_internal_schema_and_preview_do_not_expose_garmin_payload_fields() -> None:
    preview = preview_running_workout(validate(definition([executable()])))
    public_schema = repr(WorkoutDefinition.model_json_schema())

    assert preview["uploaded"] is False
    assert preview["scheduled"] is False
    assert preview["status"] == "preview_only"
    assert "not been uploaded or scheduled" in preview["message"]
    rendered = repr(preview)
    assert "workoutSegments" not in rendered
    assert "workoutTargetTypeId" not in rendered
    assert "owner" not in rendered.casefold()
    assert "url" not in rendered.casefold()
    assert "workoutSegments" not in public_schema
    assert "workoutTargetTypeId" not in public_schema


@pytest.mark.parametrize(
    "raw",
    [
        {"name": "Synthetic Builder Fixture", "steps": []},
        definition([{"step_type": "unknown", "duration": time_duration()}]),
        {**definition([executable()]), "unknown": True},
        {**definition([executable()]), "sport_type": "cycling"},
        {**definition([executable()]), "name": " padded"},
        {**definition([executable()]), "name": "bad\nname"},
        {**definition([executable()]), "name": "x" * (MAX_NAME_LENGTH + 1)},
        {
            **definition([executable()]),
            "description": "x" * (MAX_DESCRIPTION_LENGTH + 1),
        },
        {**definition([executable()]), "description": ""},
    ],
)
def test_malformed_workouts_are_rejected(raw: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        validate(raw)


@pytest.mark.parametrize(
    "duration",
    [
        {"duration_type": "time"},
        {"duration_type": "time", "duration_s": 60, "distance_m": 100},
        {"duration_type": "distance"},
        {"duration_type": "distance", "distance_m": 100, "duration_s": 60},
        {"duration_type": "open", "duration_s": 60},
        {"duration_type": "unsupported"},
        {"duration_type": "open", "unknown": 1},
        {"duration_type": "time", "duration_s": 0},
        {"duration_type": "time", "duration_s": -1},
        {"duration_type": "time", "duration_s": math.inf},
        {"duration_type": "time", "duration_s": math.nan},
        {"duration_type": "time", "duration_s": MAX_STEP_DURATION_S + 1},
        {"duration_type": "distance", "distance_m": 0},
        {"duration_type": "distance", "distance_m": -1},
        {"duration_type": "distance", "distance_m": math.inf},
        {"duration_type": "distance", "distance_m": math.nan},
        {"duration_type": "distance", "distance_m": MAX_STEP_DISTANCE_M + 1},
        {"duration_type": "distance", "distance_m": "400"},
        {"duration_type": "distance", "distance_m": True},
        {"duration_type": "time", "duration_s": "60"},
        {"duration_type": "time", "duration_s": True},
    ],
)
def test_invalid_duration_definitions_are_rejected(
    duration: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        validate(definition([executable(duration=duration)]))


@pytest.mark.parametrize(
    "target",
    [
        {"target_type": "unsupported"},
        {"target_type": "none", "unknown": 1},
        {"target_type": "none", "minimum_heart_rate_bpm": 100},
        {"target_type": "heart_rate_range"},
        {
            "target_type": "heart_rate_range",
            "minimum_heart_rate_bpm": 160,
            "maximum_heart_rate_bpm": 150,
        },
        {
            "target_type": "heart_rate_range",
            "minimum_heart_rate_bpm": 150,
            "maximum_heart_rate_bpm": 150,
        },
        {
            "target_type": "heart_rate_range",
            "minimum_heart_rate_bpm": 29,
            "maximum_heart_rate_bpm": 150,
        },
        {
            "target_type": "heart_rate_range",
            "minimum_heart_rate_bpm": 140,
            "maximum_heart_rate_bpm": 251,
        },
        {
            "target_type": "heart_rate_range",
            "minimum_heart_rate_bpm": True,
            "maximum_heart_rate_bpm": 150,
        },
        {
            "target_type": "heart_rate_range",
            "minimum_heart_rate_bpm": "140",
            "maximum_heart_rate_bpm": 150,
        },
        {
            "target_type": "pace_range",
            "minimum_pace_s_per_km": 360,
            "maximum_pace_s_per_km": 300,
        },
        {
            "target_type": "pace_range",
            "minimum_pace_s_per_km": 300,
            "maximum_pace_s_per_km": 300,
        },
        {
            "target_type": "pace_range",
            "minimum_pace_s_per_km": 0,
            "maximum_pace_s_per_km": 300,
        },
        {
            "target_type": "pace_range",
            "minimum_pace_s_per_km": -1,
            "maximum_pace_s_per_km": 300,
        },
        {
            "target_type": "pace_range",
            "minimum_pace_s_per_km": 119,
            "maximum_pace_s_per_km": 300,
        },
        {
            "target_type": "pace_range",
            "minimum_pace_s_per_km": 300,
            "maximum_pace_s_per_km": 1801,
        },
        {
            "target_type": "pace_range",
            "minimum_pace_s_per_km": 300,
            "maximum_pace_s_per_km": math.inf,
        },
        {
            "target_type": "pace_range",
            "minimum_pace_s_per_km": 300,
            "maximum_pace_s_per_km": math.nan,
        },
        {
            "target_type": "pace_range",
            "minimum_pace_s_per_km": 300,
            "maximum_pace_s_per_km": True,
        },
        {
            "target_type": "pace_range",
            "minimum_pace_s_per_km": 300,
            "maximum_pace_s_per_km": "330",
        },
        {
            "target_type": "pace_range",
            "minimum_pace_s_per_km": 300,
            "maximum_pace_s_per_km": 330,
            "minimum_heart_rate_bpm": 140,
        },
    ],
)
def test_invalid_target_definitions_are_rejected(target: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        validate(definition([executable(target=target)]))


@pytest.mark.parametrize(
    "step",
    [
        {"step_type": "run"},
        {"step_type": "run", "duration": time_duration(), "unknown": 1},
        {"step_type": "run", "duration": time_duration(), "repeat_count": 2},
        {"step_type": "run", "duration": time_duration(), "steps": [executable()]},
        {"step_type": "repeat", "repeat_count": 2, "steps": []},
        {"step_type": "repeat", "repeat_count": 1, "steps": [executable()]},
        {
            "step_type": "repeat",
            "repeat_count": MAX_REPEAT_COUNT + 1,
            "steps": [executable()],
        },
        {"step_type": "repeat", "repeat_count": True, "steps": [executable()]},
        {"step_type": "repeat", "repeat_count": "2", "steps": [executable()]},
        {
            "step_type": "repeat",
            "repeat_count": 2,
            "steps": [executable()],
            "duration": time_duration(),
        },
        {
            "step_type": "repeat",
            "repeat_count": 2,
            "steps": [executable()],
            "target": {"target_type": "none"},
        },
    ],
)
def test_invalid_step_and_repeat_shapes_are_rejected(step: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        validate(definition([step]))


def test_maximum_expanded_size_boundary_is_enforced() -> None:
    at_limit = validate(
        definition(
            [
                {
                    "step_type": "repeat",
                    "repeat_count": MAX_REPEAT_COUNT,
                    "steps": [executable(), executable("recovery")],
                }
            ]
        )
    )
    assert aggregate_workout(at_limit)["expanded_step_count"] == (
        MAX_EXPANDED_STEP_COUNT
    )

    raw = definition(
        [
            {
                "step_type": "repeat",
                "repeat_count": MAX_REPEAT_COUNT,
                "steps": [executable(), executable("recovery")],
            },
            executable("cooldown"),
        ]
    )
    with pytest.raises(ValidationError, match="expanded step count"):
        validate(raw)


def test_exact_text_and_per_step_measurement_limits_are_accepted() -> None:
    timed = validate(
        {
            "name": "n" * MAX_NAME_LENGTH,
            "description": "d" * MAX_DESCRIPTION_LENGTH,
            "steps": [executable(duration=time_duration(MAX_STEP_DURATION_S))],
        }
    )
    distanced = validate(
        definition([executable(duration=distance_duration(MAX_STEP_DISTANCE_M))])
    )

    assert aggregate_workout(timed)["total_duration_s"] == MAX_STEP_DURATION_S
    assert aggregate_workout(distanced)["total_distance_m"] == MAX_STEP_DISTANCE_M


@pytest.mark.parametrize(
    ("duration", "limit", "message"),
    [
        (time_duration(MAX_TOTAL_DURATION_S / MAX_REPEAT_COUNT), 1.0, "duration"),
        (
            distance_duration(MAX_TOTAL_DISTANCE_M / MAX_REPEAT_COUNT),
            1.0,
            "distance",
        ),
    ],
)
def test_maximum_aggregate_measurement_boundaries(
    duration: dict[str, object], limit: float, message: str
) -> None:
    raw = definition(
        [
            {
                "step_type": "repeat",
                "repeat_count": MAX_REPEAT_COUNT,
                "steps": [executable(duration=duration)],
            }
        ]
    )
    validate(raw)

    measurement_key = "duration_s" if message == "duration" else "distance_m"
    duration[measurement_key] = float(duration[measurement_key]) + limit
    with pytest.raises(ValidationError, match=message):
        validate(raw)


def test_preview_tool_has_no_garmin_client_or_write_reachability(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forbidden_client() -> Any:
        raise AssertionError("Garmin client must not be constructed")

    monkeypatch.setattr(server, "_client", forbidden_client)
    raw = definition([executable()])

    result = server.garmin_preview_running_workout(validate(raw))

    assert result["status"] == "preview_only"
    assert result["uploaded"] is False
    assert result["scheduled"] is False


def test_preview_tool_validates_through_offline_mcp_without_a_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        server,
        "_client",
        lambda: (_ for _ in ()).throw(AssertionError("unexpected Garmin client call")),
    )

    async def call_preview() -> Any:
        return await server.mcp.call_tool(
            "garmin_preview_running_workout",
            {"definition": definition([executable()])},
        )

    _, result = anyio.run(call_preview)

    assert result["status"] == "preview_only"


@pytest.mark.parametrize(
    "bad_value",
    ["300", True],
)
def test_preview_mcp_rejects_coercible_duration_values(
    bad_value: object,
) -> None:
    raw = definition([executable(duration=time_duration(bad_value))])

    async def call_preview() -> Any:
        return await server.mcp.call_tool(
            "garmin_preview_running_workout", {"definition": raw}
        )

    with pytest.raises(ToolError):
        anyio.run(call_preview)
