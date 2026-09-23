"""Validated edit-plan executor and explicit trusted tool router."""

from __future__ import annotations

import logging
import shutil
import tempfile
from pathlib import Path
from typing import Callable, Mapping

from pydantic import ValidationError

from schemas import (
    ConcatAction,
    EditPlan,
    SlowMotionAction,
    SpeedAction,
    TransitionAction,
    TrimAction,
)
from tools.audio_tools import mix_music, normalize_audio
from tools.video_tools import (
    VideoToolError,
    add_transition,
    change_speed,
    concat_clips,
    probe_video,
    slow_motion,
    trim_video,
)

LOGGER = logging.getLogger(__name__)


class PlanValidationError(ValueError):
    """Raised when untrusted plan data does not satisfy the edit contract."""


ACTION_HANDLERS: dict[str, Callable[..., Path]] = {
    "trim": trim_video,
    "slow_motion": slow_motion,
    "speed": change_speed,
    "transition": add_transition,
    "concat": concat_clips,
}


def validate_plan(plan: EditPlan | object) -> EditPlan:
    if isinstance(plan, EditPlan):
        return plan
    try:
        return EditPlan.model_validate(plan)
    except ValidationError as error:
        raise PlanValidationError(f"Invalid edit plan: {error}") from error


def _source_map(input_paths: str | Path | Mapping[str, str | Path]) -> dict[str, Path]:
    if isinstance(input_paths, (str, Path)):
        path = Path(input_paths)
        sources = {path.name: path, path.stem: path, "default": path}
    else:
        sources = {}
        for key, value in input_paths.items():
            path = Path(value)
            sources[str(key)] = path
            sources[path.name] = path
            sources[path.stem] = path
        if input_paths:
            sources["default"] = Path(next(iter(input_paths.values())))
    if not sources:
        raise PlanValidationError("No input video was supplied.")
    missing = next((path for path in sources.values() if not path.is_file()), None)
    if missing:
        raise PlanValidationError(f"Input video was not found: {missing}")
    return sources


def _resolve_source(action: TrimAction, sources: Mapping[str, Path]) -> Path:
    if action.source is None:
        return sources["default"]
    if action.source not in sources:
        raise PlanValidationError(f"Plan references unknown source '{action.source}'.")
    return sources[action.source]


def _check_range(start: float, end: float, path: Path) -> None:
    duration = float(probe_video(path)["duration"])
    if start >= duration or end > duration + 0.1:
        raise PlanValidationError(
            f"Clip range {start:g}-{end:g}s exceeds {path.name}'s {duration:.2f}s duration."
        )


def execute_plan(
    plan: EditPlan | object,
    input_paths: str | Path | Mapping[str, str | Path],
    output_path: str | Path,
    *,
    temp_root: str | Path | None = None,
    music_path: str | Path | None = None,
    music_volume: float = 0.25,
    progress: Callable[[str], None] | None = None,
) -> Path:
    """Execute only validated actions and return an existing final MP4 path."""
    edit_plan = validate_plan(plan)
    sources = _source_map(input_paths)
    final_path = Path(output_path)
    final_path.parent.mkdir(parents=True, exist_ok=True)
    notify = progress or (lambda _stage: None)
    temp_parent = Path(temp_root) if temp_root else final_path.parent
    temp_parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="montage_", dir=temp_parent) as directory:
        work_dir = Path(directory)
        pending: list[Path] = []
        current: Path | None = None
        transition_style = "fade"
        transition_duration = 0.25

        for index, action in enumerate(edit_plan.actions):
            output = work_dir / f"artifact_{index:03d}_{action.type}.mp4"
            LOGGER.info("edit_action_start index=%d type=%s", index, action.type)
            if isinstance(action, TrimAction):
                source = _resolve_source(action, sources)
                _check_range(action.start, action.end, source)
                notify(f"Extracting clip {len(pending) + 1}")
                ACTION_HANDLERS["trim"](source, output, action.start, action.end)
                pending.append(output)
                current = output
            elif isinstance(action, (SlowMotionAction, SpeedAction)):
                if current is None:
                    raise PlanValidationError(f"'{action.type}' requires a preceding clip.")
                notify("Applying speed effect")
                ACTION_HANDLERS[action.type](
                    current, output, action.speed, action.start, action.end
                )
                current = output
                if pending:
                    pending[-1] = output
            elif isinstance(action, TransitionAction):
                transition_style = action.style
                transition_duration = action.duration
                if len(pending) <= 1 and current is not None:
                    notify("Applying fade")
                    ACTION_HANDLERS["transition"](current, output, action.duration)
                    current = output
                    if pending:
                        pending[-1] = output
            elif isinstance(action, ConcatAction):
                if len(pending) < 2:
                    raise PlanValidationError("concat requires at least two prepared clips")
                notify("Combining montage")
                ACTION_HANDLERS["concat"](
                    pending,
                    output,
                    transition=transition_style,
                    transition_duration=transition_duration,
                )
                current = output
                pending = [output]
            LOGGER.info("edit_action_complete index=%d type=%s", index, action.type)

        if current is None:
            raise PlanValidationError("The edit plan produced no video artifact.")
        if len(pending) > 1:
            raise PlanValidationError("Multiple clips remain uncombined; the plan needs concat.")
        if music_path is not None:
            music = Path(music_path)
            if not music.is_file():
                raise PlanValidationError(f"Background music was not found: {music}")
            notify("Mixing background music")
            current = mix_music(
                current, music, work_dir / "artifact_music.mp4", music_volume=music_volume
            )

        normalized = normalize_audio(current, work_dir / "artifact_final.mp4")
        staging = final_path.with_suffix(final_path.suffix + ".partial")
        shutil.copy2(normalized, staging)
        staging.replace(final_path)

    if not final_path.is_file() or final_path.stat().st_size == 0:
        raise VideoToolError("Rendering completed without producing a valid output file.")
    notify("Complete")
    return final_path


__all__ = [
    "ACTION_HANDLERS",
    "PlanValidationError",
    "VideoToolError",
    "execute_plan",
    "validate_plan",
]
