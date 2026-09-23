import pytest
from pydantic import ValidationError

from schemas import EditPlan, VideoAnalysis


def test_video_analysis_accepts_optional_event_fields():
    analysis = VideoAnalysis.model_validate({"events": [{"type": "kill", "timestamp": 2.5}]})
    assert analysis.events[0].confidence is None


@pytest.mark.parametrize(
    "payload",
    [
        {"events": [{"type": "kill", "timestamp": -1}]},
        {"events": [{"type": "invented", "timestamp": 1}]},
    ],
)
def test_invalid_events_are_rejected(payload):
    with pytest.raises(ValidationError):
        VideoAnalysis.model_validate(payload)


def test_edit_plan_uses_discriminated_actions():
    plan = EditPlan.model_validate(
        {
            "actions": [
                {"type": "trim", "start": 1, "end": 3},
                {"type": "trim", "start": 8, "end": 10},
                {"type": "transition", "duration": 0.2},
                {"type": "concat"},
            ]
        }
    )
    assert [action.type for action in plan.actions] == ["trim", "trim", "transition", "concat"]


@pytest.mark.parametrize(
    "action",
    [
        {"type": "trim", "start": 5, "end": 5},
        {"type": "slow_motion", "start": 0, "end": 2, "speed": 1.2},
        {"type": "transition", "duration": 20},
        {"type": "run_shell", "command": "rm -rf /"},
    ],
)
def test_invalid_actions_are_rejected(action):
    with pytest.raises(ValidationError):
        EditPlan.model_validate({"actions": [action]})


def test_multiple_trims_require_concat():
    with pytest.raises(ValidationError, match="concat"):
        EditPlan.model_validate(
            {
                "actions": [
                    {"type": "trim", "start": 0, "end": 1},
                    {"type": "trim", "start": 2, "end": 3},
                ]
            }
        )
