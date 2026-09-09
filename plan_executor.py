"""Validation and execution for Gemini-generated edit plans."""

from numbers import Real
from pathlib import Path

from video_tools import trim_video


class PlanValidationError(ValueError):
    """Raised when a planner response is not a supported edit plan."""


ACTION_HANDLERS = {
    "trim": trim_video,
}


def validate_plan(plan: object) -> dict:
    if not isinstance(plan, dict):
        raise PlanValidationError("Gemini response must be a JSON object.")

    actions = plan.get("actions")
    if not isinstance(actions, list):
        raise PlanValidationError("The plan must contain an 'actions' list.")
    if not actions:
        raise PlanValidationError("The plan must contain at least one action.")
    if len(actions) > 1:
        raise PlanValidationError(
            "This first version supports one action at a time; use one trim action."
        )

    for index, action in enumerate(actions):
        if not isinstance(action, dict):
            raise PlanValidationError(f"Action {index + 1} must be a JSON object.")

        action_type = action.get("type")
        if not isinstance(action_type, str):
            raise PlanValidationError(f"Action {index + 1} must contain a 'type'.")
        if action_type not in ACTION_HANDLERS:
            raise PlanValidationError(
                f"Unsupported action type '{action_type}'. "
                f"Supported type: {', '.join(ACTION_HANDLERS)}."
            )

        start = action.get("start")
        end = action.get("end")
        if isinstance(start, bool) or not isinstance(start, Real):
            raise PlanValidationError("Trim action 'start' must be numeric.")
        if isinstance(end, bool) or not isinstance(end, Real):
            raise PlanValidationError("Trim action 'end' must be numeric.")
        if start < 0:
            raise PlanValidationError("Trim action 'start' cannot be negative.")
        if end <= start:
            raise PlanValidationError("Trim action 'end' must be greater than 'start'.")

    return plan


def execute_plan(plan: dict, input_path: Path, output_path: Path) -> None:
    """Execute a validated plan using only predefined Python tools."""
    validate_plan(plan)

    for action in plan["actions"]:
        if action["type"] == "trim":
            ACTION_HANDLERS["trim"](
                input_path=input_path,
                output_path=output_path,
                start=float(action["start"]),
                end=float(action["end"]),
            )
        else:
            raise PlanValidationError(
                f"Unsupported action type '{action['type']}'. "
                f"Supported type: {', '.join(ACTION_HANDLERS)}."
            )

