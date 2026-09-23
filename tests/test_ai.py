from types import SimpleNamespace

import pytest
from google.genai import errors, types

from ai.common import AIResponseError, parse_model_response
from ai.edit_planner import EditingPlanner
from ai.video_analyzer import (
    GeminiVideoAnalyzer,
    VideoAnalysisError,
    gemini_response_schema,
)
from schemas import EditPlan, VideoAnalysis


class Files:
    def __init__(self):
        self.deleted = False
        self.upload_count = 0

    def upload(self, file):
        self.upload_count += 1
        return types.File(
            name="files/1",
            uri="https://generativelanguage.googleapis.com/v1beta/files/1",
            mime_type="video/mp4",
            state="PROCESSING",
        )

    def get(self, name):
        return types.File(
            name=name,
            uri="https://generativelanguage.googleapis.com/v1beta/files/1",
            mime_type="video/mp4",
            state="ACTIVE",
        )

    def delete(self, name):
        self.deleted = True


class Models:
    def __init__(self, text, failures=None):
        self.text = text
        self.failures = list(failures or [])
        self.call_count = 0
        self.calls = []

    def generate_content(self, **kwargs):
        self.call_count += 1
        self.calls.append(kwargs)
        if self.failures:
            raise self.failures.pop(0)
        return SimpleNamespace(text=self.text, parsed=None)


def api_error(code):
    error_type = errors.ClientError if code < 500 else errors.ServerError
    status = "INVALID_ARGUMENT" if code == 400 else "UNAVAILABLE"
    return error_type(code, {"error": {"code": code, "status": status}})


def analyzer(client, *, attempts=5, sleeps=None):
    sleeps = sleeps if sleeps is not None else []
    return GeminiVideoAnalyzer(
        "",
        client=client,
        poll_interval=0,
        max_generation_attempts=attempts,
        sleep=sleeps.append,
        jitter=lambda: 0.3,
    )


def test_analyzer_uploads_waits_parses_and_deletes(tmp_path):
    video = tmp_path / "clip.mp4"
    video.write_bytes(b"not decoded by mocked client")
    client = SimpleNamespace(
        files=Files(), models=Models('{"events":[{"type":"kill","timestamp":1.2}]}')
    )
    result = GeminiVideoAnalyzer(
        "", client=client, poll_interval=0, sleep=lambda _: None
    ).analyze_video(video)
    assert result.events[0].type == "kill"
    assert client.files.deleted
    request = client.models.calls[0]
    assert request["contents"][0].uri.endswith("/files/1")
    assert request["contents"][0].mime_type == "video/mp4"
    assert request["contents"][1].startswith("Analyze this Valorant gameplay video")
    config = request["config"]
    assert isinstance(config, types.GenerateContentConfig)
    assert config.response_mime_type == "application/json"
    assert config.response_schema is None
    assert config.tools is None
    assert config.automatic_function_calling.disable is True


def test_gemini_schema_removes_additional_properties_recursively():
    raw_schema = VideoAnalysis.model_json_schema()
    assert raw_schema["additionalProperties"] is False
    assert raw_schema["$defs"]["VideoEvent"]["additionalProperties"] is False

    schema = gemini_response_schema(VideoAnalysis)

    def assert_supported(value):
        if isinstance(value, dict):
            assert "additionalProperties" not in value
            assert "additional_properties" not in value
            for child in value.values():
                assert_supported(child)
        elif isinstance(value, list):
            for child in value:
                assert_supported(child)

    assert_supported(schema)
    event_schema = schema["$defs"]["VideoEvent"]
    assert event_schema["type"] == "object"
    assert set(event_schema["required"]) == {"type", "timestamp"}
    assert schema["properties"]["events"]["items"]["$ref"].endswith("/VideoEvent")


def test_plain_multimodal_smoke_request_has_no_generation_config():
    client = SimpleNamespace(files=Files(), models=Models("A player gets a kill."))
    analyzer_instance = analyzer(client)
    uploaded = client.files.get("files/1")

    response = analyzer_instance._generate_content(
        uploaded, "Describe what happens in this video."
    )

    assert response.text == "A player gets a kill."
    assert client.models.calls == [
        {
            "model": "gemini-3.6-flash",
            "contents": [uploaded, "Describe what happens in this video."],
        }
    ]


def test_structured_response_uses_validated_video_analysis(tmp_path):
    video = tmp_path / "clip.mp4"
    video.write_bytes(b"video")
    parsed = VideoAnalysis.model_validate(
        {"events": [{"type": "kill", "timestamp": 42.3, "source": "gemini"}]}
    )
    models = Models("")
    models.text = None

    def generate_content(**kwargs):
        models.call_count += 1
        models.calls.append(kwargs)
        return SimpleNamespace(text=None, parsed=parsed)

    models.generate_content = generate_content
    client = SimpleNamespace(files=Files(), models=models)

    result = analyzer(client).analyze_video(video)

    assert result == parsed
    assert client.files.deleted


def test_malformed_structured_response_is_rejected_and_cleaned_up(tmp_path):
    video = tmp_path / "clip.mp4"
    video.write_bytes(b"video")
    client = SimpleNamespace(files=Files(), models=Models("not json"))

    with pytest.raises(VideoAnalysisError, match="malformed JSON"):
        analyzer(client).analyze_video(video)

    assert client.files.deleted


def test_unexpected_structured_response_field_is_rejected_and_cleaned_up(tmp_path):
    video = tmp_path / "clip.mp4"
    video.write_bytes(b"video")
    client = SimpleNamespace(
        files=Files(),
        models=Models(
            '{"events":[{"type":"kill","timestamp":1,"unexpected":"rejected"}]}'
        ),
    )

    with pytest.raises(VideoAnalysisError, match="schema validation"):
        analyzer(client).analyze_video(video)

    assert client.files.deleted


def test_first_503_retries_then_succeeds_without_reupload(tmp_path):
    video = tmp_path / "clip.mp4"
    video.write_bytes(b"video")
    client = SimpleNamespace(
        files=Files(),
        models=Models('{"events":[]}', [api_error(503)]),
    )
    sleeps = []

    result = analyzer(client, sleeps=sleeps).analyze_video(video)

    assert result.events == []
    assert client.models.call_count == 2
    assert client.files.upload_count == 1
    assert [delay for delay in sleeps if delay] == [2.3]
    assert client.files.deleted


def test_multiple_503s_retry_then_succeed(tmp_path):
    video = tmp_path / "clip.mp4"
    video.write_bytes(b"video")
    client = SimpleNamespace(
        files=Files(),
        models=Models('{"events":[]}', [api_error(503), api_error(503), api_error(503)]),
    )
    sleeps = []

    analyzer(client, sleeps=sleeps).analyze_video(video)

    assert client.models.call_count == 4
    assert [delay for delay in sleeps if delay] == [2.3, 4.3, 8.3]
    assert client.files.upload_count == 1
    assert client.files.deleted


def test_retries_exhausted_and_remote_file_is_deleted(tmp_path):
    video = tmp_path / "clip.mp4"
    video.write_bytes(b"video")
    client = SimpleNamespace(
        files=Files(),
        models=Models('{"events":[]}', [api_error(503)] * 3),
    )

    with pytest.raises(VideoAnalysisError, match="temporarily unavailable after 3 attempts"):
        analyzer(client, attempts=3).analyze_video(video)

    assert client.models.call_count == 3
    assert client.files.upload_count == 1
    assert client.files.deleted


def test_permanent_400_does_not_retry_and_remote_file_is_deleted(tmp_path):
    video = tmp_path / "clip.mp4"
    video.write_bytes(b"video")
    client = SimpleNamespace(
        files=Files(), models=Models('{"events":[]}', [api_error(400)])
    )
    sleeps = []

    with pytest.raises(VideoAnalysisError, match="Gemini could not analyze"):
        analyzer(client, sleeps=sleeps).analyze_video(video)

    assert client.models.call_count == 1
    assert [delay for delay in sleeps if delay] == []
    assert client.files.upload_count == 1
    assert client.files.deleted


def test_analyzer_uses_gemini_model_environment_variable(monkeypatch):
    monkeypatch.setenv("GEMINI_MODEL", "gemini-test-model")
    client = SimpleNamespace(files=Files(), models=Models('{"events":[]}'))

    assert GeminiVideoAnalyzer("", client=client).model == "gemini-test-model"


def test_planner_parses_validated_plan():
    client = SimpleNamespace(
        files=Files(), models=Models('{"actions":[{"type":"trim","start":0,"end":2}]}')
    )
    analysis = VideoAnalysis.model_validate({"events": [{"type": "kill", "timestamp": 1}]})
    result = EditingPlanner("", client=client).create_plan("make a clip", analysis)
    assert isinstance(result, EditPlan)


def test_malformed_response_is_rejected():
    with pytest.raises(AIResponseError, match="malformed"):
        parse_model_response(SimpleNamespace(text="not json", parsed=None), VideoAnalysis)
