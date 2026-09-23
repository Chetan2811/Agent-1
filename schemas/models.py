"""Pydantic models for gameplay understanding and deterministic edit plans."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

GameplayEventType = Literal[
    "kill",
    "headshot",
    "double_kill",
    "triple_kill",
    "quad_kill",
    "ace",
    "death",
    "clutch",
    "round_win",
    "other",
]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class VideoEvent(StrictModel):
    type: GameplayEventType
    timestamp: float = Field(ge=0)
    confidence: float | None = Field(default=None, ge=0, le=1)
    description: str | None = Field(default=None, max_length=500)
    source: str | None = Field(default="gemini", max_length=255)


class VideoAnalysis(StrictModel):
    events: list[VideoEvent] = Field(default_factory=list, max_length=500)


class TrimAction(StrictModel):
    type: Literal["trim"] = "trim"
    start: float = Field(ge=0)
    end: float = Field(gt=0)
    source: str | None = Field(default=None, max_length=255)

    @model_validator(mode="after")
    def validate_range(self) -> "TrimAction":
        if self.end <= self.start:
            raise ValueError("end must be greater than start")
        return self


class SlowMotionAction(StrictModel):
    type: Literal["slow_motion"] = "slow_motion"
    start: float = Field(default=0, ge=0)
    end: float | None = Field(default=None, gt=0)
    speed: float = Field(gt=0, lt=1)

    @model_validator(mode="after")
    def validate_range(self) -> "SlowMotionAction":
        if self.end is not None and self.end <= self.start:
            raise ValueError("end must be greater than start")
        return self


class SpeedAction(StrictModel):
    type: Literal["speed"] = "speed"
    start: float = Field(default=0, ge=0)
    end: float | None = Field(default=None, gt=0)
    speed: float = Field(gt=0, le=4)

    @model_validator(mode="after")
    def validate_range(self) -> "SpeedAction":
        if self.end is not None and self.end <= self.start:
            raise ValueError("end must be greater than start")
        return self


class TransitionAction(StrictModel):
    type: Literal["transition"] = "transition"
    style: Literal["fade", "fadeblack", "dissolve", "wipeleft", "slideright"] = "fade"
    duration: float = Field(default=0.25, ge=0.05, le=2)


class ConcatAction(StrictModel):
    type: Literal["concat"] = "concat"


EditAction = Annotated[
    TrimAction | SlowMotionAction | SpeedAction | TransitionAction | ConcatAction,
    Field(discriminator="type"),
]


class EditPlan(StrictModel):
    actions: list[EditAction] = Field(min_length=1, max_length=50)

    @model_validator(mode="after")
    def validate_sequence(self) -> "EditPlan":
        trim_count = sum(isinstance(action, TrimAction) for action in self.actions)
        concat_count = sum(isinstance(action, ConcatAction) for action in self.actions)
        if trim_count == 0:
            raise ValueError("a plan must contain at least one trim action")
        if concat_count > 1:
            raise ValueError("a plan may contain at most one concat action")
        if trim_count > 1 and concat_count != 1:
            raise ValueError("plans with multiple trims require exactly one concat action")
        if concat_count and trim_count < 2:
            raise ValueError("concat requires at least two trim actions")
        if concat_count:
            concat_index = next(
                index
                for index, action in enumerate(self.actions)
                if isinstance(action, ConcatAction)
            )
            if any(isinstance(action, TrimAction) for action in self.actions[concat_index + 1 :]):
                raise ValueError("trim actions must precede concat")
        has_artifact = False
        for action in self.actions:
            if isinstance(action, (TrimAction, ConcatAction)):
                has_artifact = True
            elif isinstance(action, (SlowMotionAction, SpeedAction)) and not has_artifact:
                raise ValueError(f"{action.type} requires a preceding trim")
        return self
