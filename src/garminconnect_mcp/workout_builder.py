from __future__ import annotations

import math
import unicodedata
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

MAX_NAME_LENGTH = 80
MAX_DESCRIPTION_LENGTH = 500
MAX_STEP_DURATION_S = 86_400.0
MAX_STEP_DISTANCE_M = 100_000.0
MAX_REPEAT_COUNT = 50
MAX_REPEAT_NESTING_DEPTH = 2
MAX_STRUCTURAL_STEP_COUNT = 100
MAX_EXPANDED_STEP_COUNT = 100
MAX_TOTAL_DURATION_S = 604_800.0
MAX_TOTAL_DISTANCE_M = 1_000_000.0


class WorkoutDefinitionError(ValueError):
    """Raised when a running-workout definition exceeds a safety boundary."""


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class DurationDefinition(StrictModel):
    """Exactly one explicit-unit end condition for an executable step."""

    duration_type: Literal["time", "distance", "open"]
    duration_s: float | None = Field(
        default=None, gt=0, le=MAX_STEP_DURATION_S, allow_inf_nan=False
    )
    distance_m: float | None = Field(
        default=None, gt=0, le=MAX_STEP_DISTANCE_M, allow_inf_nan=False
    )

    @model_validator(mode="after")
    def validate_measurement(self) -> DurationDefinition:
        if self.duration_type == "time":
            if self.duration_s is None or self.distance_m is not None:
                raise ValueError("time duration requires only duration_s")
        elif self.duration_type == "distance":
            if self.distance_m is None or self.duration_s is not None:
                raise ValueError("distance duration requires only distance_m")
        elif self.duration_s is not None or self.distance_m is not None:
            raise ValueError("open duration does not accept a measurement")
        return self


class TargetDefinition(StrictModel):
    """One verified running target, expressed only in canonical public units."""

    target_type: Literal["none", "heart_rate_range", "pace_range"]
    minimum_heart_rate_bpm: int | None = Field(default=None, strict=True, ge=30, le=250)
    maximum_heart_rate_bpm: int | None = Field(default=None, strict=True, ge=30, le=250)
    minimum_pace_s_per_km: float | None = Field(
        default=None, gt=0, ge=120, le=1_800, allow_inf_nan=False
    )
    maximum_pace_s_per_km: float | None = Field(
        default=None, gt=0, ge=120, le=1_800, allow_inf_nan=False
    )

    @model_validator(mode="after")
    def validate_range(self) -> TargetDefinition:
        heart_rate_values = (
            self.minimum_heart_rate_bpm,
            self.maximum_heart_rate_bpm,
        )
        pace_values = (self.minimum_pace_s_per_km, self.maximum_pace_s_per_km)

        if self.target_type == "none":
            if any(value is not None for value in heart_rate_values + pace_values):
                raise ValueError("no-target definition does not accept range fields")
        elif self.target_type == "heart_rate_range":
            if None in heart_rate_values or any(
                value is not None for value in pace_values
            ):
                raise ValueError(
                    "heart_rate_range requires only minimum_heart_rate_bpm and "
                    "maximum_heart_rate_bpm"
                )
            if heart_rate_values[0] >= heart_rate_values[1]:
                raise ValueError(
                    "heart-rate range must increase from minimum to maximum"
                )
        else:
            if None in pace_values or any(
                value is not None for value in heart_rate_values
            ):
                raise ValueError(
                    "pace_range requires only minimum_pace_s_per_km and "
                    "maximum_pace_s_per_km"
                )
            if pace_values[0] >= pace_values[1]:
                raise ValueError("pace range must increase from minimum to maximum")
        return self


class WorkoutStep(StrictModel):
    """Executable running step or bounded repeat group."""

    step_type: Literal["warmup", "run", "recovery", "cooldown", "repeat"]
    duration: DurationDefinition | None = None
    target: TargetDefinition | None = None
    repeat_count: int | None = Field(
        default=None, strict=True, ge=2, le=MAX_REPEAT_COUNT
    )
    steps: list[WorkoutStep] | None = None

    @model_validator(mode="after")
    def validate_shape(self) -> WorkoutStep:
        if self.step_type == "repeat":
            if self.duration is not None or self.target is not None:
                raise ValueError("repeat steps do not accept duration or target")
            if self.repeat_count is None:
                raise ValueError("repeat steps require repeat_count")
            if not self.steps:
                raise ValueError("repeat steps require a non-empty nested sequence")
        elif self.duration is None:
            raise ValueError("executable steps require exactly one duration definition")
        elif self.repeat_count is not None or self.steps is not None:
            raise ValueError("only repeat steps accept repeat_count or nested steps")
        return self


class WorkoutDefinition(StrictModel):
    """Safe internal definition for one structured running workout."""

    sport_type: Literal["running"] = "running"
    name: str = Field(min_length=1, max_length=MAX_NAME_LENGTH, strict=True)
    description: str | None = Field(
        default=None, min_length=1, max_length=MAX_DESCRIPTION_LENGTH, strict=True
    )
    steps: list[WorkoutStep] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_workout(self) -> WorkoutDefinition:
        _validate_text(self.name, field="name")
        if self.description is not None:
            _validate_text(self.description, field="description")
        _validate_safety_limits(self.steps)
        return self


WorkoutStep.model_rebuild()


def _validate_text(value: str, *, field: str) -> None:
    if value != value.strip():
        raise ValueError(f"{field} must not have leading or trailing whitespace")
    if any(unicodedata.category(character).startswith("C") for character in value):
        raise ValueError(f"{field} must not contain control characters")


def _walk_structural(
    steps: list[WorkoutStep], *, repeat_depth: int = 0
) -> list[WorkoutStep]:
    result: list[WorkoutStep] = []
    for step in steps:
        result.append(step)
        if step.step_type == "repeat":
            next_depth = repeat_depth + 1
            if next_depth > MAX_REPEAT_NESTING_DEPTH:
                raise WorkoutDefinitionError(
                    f"repeat nesting depth must not exceed {MAX_REPEAT_NESTING_DEPTH}"
                )
            result.extend(_walk_structural(step.steps or [], repeat_depth=next_depth))
    return result


def _expanded_steps(steps: list[WorkoutStep]) -> list[WorkoutStep]:
    result: list[WorkoutStep] = []
    for step in steps:
        if step.step_type == "repeat":
            nested = _expanded_steps(step.steps or [])
            result.extend(nested * (step.repeat_count or 0))
        else:
            result.append(step)
    return result


def _validate_safety_limits(steps: list[WorkoutStep]) -> None:
    structural = _walk_structural(steps)
    if len(structural) > MAX_STRUCTURAL_STEP_COUNT:
        raise WorkoutDefinitionError(
            f"structural step count must not exceed {MAX_STRUCTURAL_STEP_COUNT}"
        )

    expanded = _expanded_steps(steps)
    if len(expanded) > MAX_EXPANDED_STEP_COUNT:
        raise WorkoutDefinitionError(
            f"expanded step count must not exceed {MAX_EXPANDED_STEP_COUNT}"
        )

    known_duration_s = math.fsum(
        step.duration.duration_s
        for step in expanded
        if step.duration is not None and step.duration.duration_s is not None
    )
    known_distance_m = math.fsum(
        step.duration.distance_m
        for step in expanded
        if step.duration is not None and step.duration.distance_m is not None
    )
    if known_duration_s > MAX_TOTAL_DURATION_S:
        raise WorkoutDefinitionError(
            f"known expanded duration must not exceed {MAX_TOTAL_DURATION_S:g} seconds"
        )
    if known_distance_m > MAX_TOTAL_DISTANCE_M:
        raise WorkoutDefinitionError(
            f"known expanded distance must not exceed {MAX_TOTAL_DISTANCE_M:g} meters"
        )


def aggregate_workout(definition: WorkoutDefinition) -> dict[str, Any]:
    """Return deterministic known totals and completeness for expanded steps."""
    expanded = _expanded_steps(definition.steps)
    known_duration_s = math.fsum(
        step.duration.duration_s
        for step in expanded
        if step.duration is not None and step.duration.duration_s is not None
    )
    known_distance_m = math.fsum(
        step.duration.distance_m
        for step in expanded
        if step.duration is not None and step.duration.distance_m is not None
    )
    duration_complete = all(
        step.duration is not None and step.duration.duration_type == "time"
        for step in expanded
    )
    distance_complete = all(
        step.duration is not None and step.duration.duration_type == "distance"
        for step in expanded
    )
    return {
        "expanded_step_count": len(expanded),
        "known_duration_s": known_duration_s,
        "total_duration_s": known_duration_s if duration_complete else None,
        "duration_total_complete": duration_complete,
        "known_distance_m": known_distance_m,
        "total_distance_m": known_distance_m if distance_complete else None,
        "distance_total_complete": distance_complete,
    }


_STEP_TYPES = {
    "warmup": (1, "warmup", 1),
    "cooldown": (2, "cooldown", 2),
    "run": (3, "interval", 3),
    "recovery": (4, "recovery", 4),
    "repeat": (6, "repeat", 6),
}
_END_CONDITIONS = {
    "open": (1, "lap.button", 1),
    "time": (2, "time", 2),
    "distance": (3, "distance", 3),
}


def _target_payload(target: TargetDefinition | None) -> dict[str, Any]:
    if target is None or target.target_type == "none":
        return {
            "targetType": {
                "workoutTargetTypeId": 1,
                "workoutTargetTypeKey": "no.target",
                "displayOrder": 1,
            }
        }
    if target.target_type == "heart_rate_range":
        return {
            "targetType": {
                "workoutTargetTypeId": 4,
                "workoutTargetTypeKey": "heart.rate.zone",
            },
            "targetValueOne": target.minimum_heart_rate_bpm,
            "targetValueTwo": target.maximum_heart_rate_bpm,
        }

    minimum_pace = target.minimum_pace_s_per_km
    maximum_pace = target.maximum_pace_s_per_km
    assert minimum_pace is not None and maximum_pace is not None
    return {
        "targetType": {
            "workoutTargetTypeId": 6,
            "workoutTargetTypeKey": "pace.zone",
        },
        "targetValueOne": round(1000.0 / maximum_pace, 8),
        "targetValueTwo": round(1000.0 / minimum_pace, 8),
    }


def serialize_running_workout(definition: WorkoutDefinition) -> dict[str, Any]:
    """Serialize a validated definition without making a Garmin client call."""
    aggregates = aggregate_workout(definition)
    next_order = 0

    def serialize_steps(steps: list[WorkoutStep]) -> list[dict[str, Any]]:
        nonlocal next_order
        serialized: list[dict[str, Any]] = []
        for step in steps:
            next_order += 1
            step_order = next_order
            step_id, step_key, display_order = _STEP_TYPES[step.step_type]
            step_type = {
                "stepTypeId": step_id,
                "stepTypeKey": step_key,
                "displayOrder": display_order,
            }
            if step.step_type == "repeat":
                iterations = step.repeat_count
                serialized.append(
                    {
                        "type": "RepeatGroupDTO",
                        "stepOrder": step_order,
                        "stepType": step_type,
                        "numberOfIterations": iterations,
                        "workoutSteps": serialize_steps(step.steps or []),
                        "endCondition": {
                            "conditionTypeId": 7,
                            "conditionTypeKey": "iterations",
                            "displayOrder": 7,
                            "displayable": False,
                        },
                        "endConditionValue": float(iterations or 0),
                        "smartRepeat": False,
                    }
                )
                continue

            assert step.duration is not None
            condition_id, condition_key, condition_order = _END_CONDITIONS[
                step.duration.duration_type
            ]
            item: dict[str, Any] = {
                "type": "ExecutableStepDTO",
                "stepOrder": step_order,
                "stepType": step_type,
                "endCondition": {
                    "conditionTypeId": condition_id,
                    "conditionTypeKey": condition_key,
                    "displayOrder": condition_order,
                    "displayable": True,
                },
            }
            if step.duration.duration_type == "time":
                item["endConditionValue"] = step.duration.duration_s
            elif step.duration.duration_type == "distance":
                item["endConditionValue"] = step.duration.distance_m
            item.update(_target_payload(step.target))
            serialized.append(item)
        return serialized

    sport_type = {
        "sportTypeId": 1,
        "sportTypeKey": "running",
        "displayOrder": 1,
    }
    payload: dict[str, Any] = {
        "workoutName": definition.name,
        "sportType": sport_type,
        "estimatedDurationInSecs": math.ceil(aggregates["total_duration_s"] or 0.0),
        "estimatedDistanceInMeters": aggregates["total_distance_m"] or 0.0,
        "workoutSegments": [
            {
                "segmentOrder": 1,
                "sportType": dict(sport_type),
                "workoutSteps": serialize_steps(definition.steps),
            }
        ],
        "author": {},
    }
    if definition.description is not None:
        payload["description"] = definition.description
    return payload


def preview_running_workout(definition: WorkoutDefinition) -> dict[str, Any]:
    """Return a normalized, expanded preview without exposing Garmin JSON."""
    aggregates = aggregate_workout(definition)
    expanded_preview: list[dict[str, Any]] = []
    for order, step in enumerate(_expanded_steps(definition.steps), start=1):
        target = step.target or TargetDefinition(target_type="none")
        expanded_preview.append(
            {
                "order": order,
                "step_type": step.step_type,
                "duration": step.duration.model_dump(exclude_none=True),
                "target": target.model_dump(exclude_none=True),
            }
        )

    serialization = serialize_running_workout(definition)
    serialized_steps = serialization["workoutSegments"][0]["workoutSteps"]
    return {
        "status": "preview_only",
        "uploaded": False,
        "scheduled": False,
        "message": (
            "Validated locally; this workout has not been uploaded or scheduled."
        ),
        "definition": definition.model_dump(exclude_none=True),
        "aggregates": aggregates,
        "expanded_steps": expanded_preview,
        "serialization_diagnostic": {
            "garmin_workout_classification": "running",
            "garmin_sport_classification": "running",
            "top_level_serialized_step_count": len(serialized_steps),
        },
    }
