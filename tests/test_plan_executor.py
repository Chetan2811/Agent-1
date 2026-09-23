import shutil
from pathlib import Path

import plan_executor
from schemas import EditPlan


def test_multiple_trims_create_distinct_artifacts(monkeypatch, tmp_path):
    source = tmp_path / "source.mp4"
    source.write_bytes(b"source")
    calls = []

    def artifact(*args, **kwargs):
        output = Path(args[1])
        output.write_bytes(b"artifact")
        calls.append((args, kwargs))
        return output

    def normalize(input_path, output_path, target_lufs=-14):
        shutil.copy2(input_path, output_path)
        return Path(output_path)

    monkeypatch.setattr(plan_executor, "probe_video", lambda _: {"duration": 20})
    monkeypatch.setattr(plan_executor, "normalize_audio", normalize)
    for action in plan_executor.ACTION_HANDLERS:
        monkeypatch.setitem(plan_executor.ACTION_HANDLERS, action, artifact)

    plan = EditPlan.model_validate(
        {
            "actions": [
                {"type": "trim", "start": 0, "end": 2},
                {"type": "trim", "start": 5, "end": 7},
                {"type": "concat"},
            ]
        }
    )
    result = plan_executor.execute_plan(plan, source, tmp_path / "final.mp4", temp_root=tmp_path)
    trim_outputs = [Path(call[0][1]) for call in calls[:2]]
    assert trim_outputs[0] != trim_outputs[1]
    assert result.is_file()


def test_registry_contains_only_supported_tools():
    assert set(plan_executor.ACTION_HANDLERS) == {
        "trim",
        "slow_motion",
        "speed",
        "transition",
        "concat",
    }
