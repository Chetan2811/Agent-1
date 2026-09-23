"""Gemini multimodal video understanding with Files API lifecycle handling."""

from __future__ import annotations

import logging
import os
import random
import time
from copy import deepcopy
from pathlib import Path
from typing import Any, Callable, TypeVar

from pydantic import BaseModel

from config import DEFAULT_GEMINI_MODEL
from cv.frame_analyzer import VideoInspectionError, get_video_metadata
from schemas import VideoAnalysis

from .common import AIResponseError, parse_model_response
from .prompts import VIDEO_ANALYSIS_PROMPT

LOGGER = logging.getLogger(__name__)
TRANSIENT_GEMINI_STATUS_CODES = frozenset({429, 500, 502, 503, 504})
ResponseSchema = TypeVar("ResponseSchema", bound=BaseModel)


def gemini_response_schema(model: type[BaseModel]) -> dict[str, Any]:
    """Build a Gemini-compatible schema without weakening Pydantic validation."""
    schema = deepcopy(model.model_json_schema())

    def remove_unsupported_metadata(value: object) -> None:
        if isinstance(value, dict):
            value.pop("additionalProperties", None)
            value.pop("additional_properties", None)
            for child in value.values():
                remove_unsupported_metadata(child)
        elif isinstance(value, list):
            for child in value:
                remove_unsupported_metadata(child)

    remove_unsupported_metadata(schema)
    return schema


class VideoAnalysisError(RuntimeError):
    """Raised when upload, processing, generation, or validation fails."""


class GeminiVideoAnalyzer:
    def __init__(
        self,
        api_key: str,
        model: str | None = None,
        *,
        client: object | None = None,
        timeout_seconds: int = 600,
        poll_interval: float = 2,
        max_generation_attempts: int = 5,
        sleep: Callable[[float], None] = time.sleep,
        jitter: Callable[[], float] = random.random,
    ) -> None:
        if not api_key and client is None:
            raise ValueError("GEMINI_API_KEY is required for video analysis.")
        if client is None:
            try:
                from google import genai
            except ImportError as error:
                raise RuntimeError("Install google-genai to use Gemini analysis.") from error
            client = genai.Client(api_key=api_key)
        self.client = client
        self.model = model or os.getenv("GEMINI_MODEL", DEFAULT_GEMINI_MODEL)
        self.timeout_seconds = timeout_seconds
        self.poll_interval = poll_interval
        if max_generation_attempts < 1:
            raise ValueError("max_generation_attempts must be at least 1.")
        self.max_generation_attempts = max_generation_attempts
        self.sleep = sleep
        self.jitter = jitter

    @staticmethod
    def _state_name(uploaded: object) -> str:
        state = getattr(uploaded, "state", None)
        value = getattr(state, "name", state)
        return str(value or "UNKNOWN").upper()

    def _wait_until_ready(self, uploaded: object) -> object:
        deadline = time.monotonic() + self.timeout_seconds
        current = uploaded
        while self._state_name(current) not in {"ACTIVE", "READY"}:
            state = self._state_name(current)
            if state in {"FAILED", "ERROR", "CANCELLED"}:
                raise VideoAnalysisError(f"Gemini file processing failed with state {state}.")
            if time.monotonic() >= deadline:
                raise VideoAnalysisError(
                    f"Gemini file processing timed out after {self.timeout_seconds} seconds."
                )
            self.sleep(self.poll_interval)
            current = self.client.files.get(name=current.name)
        return current

    @staticmethod
    def _transient_status_code(error: Exception) -> int | None:
        """Return a retryable google-genai API status code, if present."""
        try:
            from google.genai import errors
        except ImportError:
            return None
        if not isinstance(error, errors.APIError):
            return None
        code = getattr(error, "code", None)
        return code if code in TRANSIENT_GEMINI_STATUS_CODES else None

    @staticmethod
    def _file_diagnostics(uploaded: object) -> tuple[str, bool]:
        return (
            str(getattr(uploaded, "mime_type", None) or "unknown"),
            bool(getattr(uploaded, "uri", None)),
        )

    def _generate_content(
        self,
        uploaded: object,
        prompt: str,
        response_schema: type[ResponseSchema] | None = None,
    ) -> object:
        """Retry only generation; the already-active remote file is reused."""
        # google-genai accepts its uploaded File directly and converts it to a
        # file_data Part using the File's uri and mime_type.
        contents = [uploaded, prompt]
        config = None
        if response_schema is not None:
            from google.genai import types

            config = types.GenerateContentConfig(
                response_mime_type="application/json",
                automatic_function_calling=types.AutomaticFunctionCallingConfig(
                    disable=True
                ),
            )
        for attempt in range(1, self.max_generation_attempts + 1):
            try:
                return self.client.models.generate_content(
                    model=self.model,
                    contents=contents,
                    **({"config": config} if config is not None else {}),
                )
            except Exception as error:
                status_code = self._transient_status_code(error)
                if status_code is None:
                    mime_type, has_uri = self._file_diagnostics(uploaded)
                    LOGGER.error(
                        "gemini_generation_rejected model=%s status=%s mime_type=%s "
                        "has_uploaded_uri=%s response_mode=%s schema=%s",
                        self.model,
                        getattr(error, "code", "unknown"),
                        mime_type,
                        has_uri,
                        "structured_json" if response_schema is not None else "plain_text",
                        response_schema.__name__ if response_schema is not None else "none",
                    )
                    raise
                if attempt == self.max_generation_attempts:
                    raise VideoAnalysisError(
                        "Gemini is temporarily unavailable after "
                        f"{self.max_generation_attempts} attempts. Please try again later."
                    ) from error
                delay = (2 ** attempt) + self.jitter()
                LOGGER.warning(
                    "Gemini unavailable (status %d). Retry %d/%d in %.1f seconds.",
                    status_code,
                    attempt + 1,
                    self.max_generation_attempts,
                    delay,
                )
                self.sleep(delay)
        raise AssertionError("generation retry loop ended unexpectedly")

    def analyze_video(self, video_path: str | Path) -> VideoAnalysis:
        path = Path(video_path)
        if not path.is_file():
            raise VideoAnalysisError(f"Video was not found: {path}")
        uploaded = None
        started = time.monotonic()
        metadata = None
        prompt = VIDEO_ANALYSIS_PROMPT
        try:
            metadata = get_video_metadata(path)
            prompt += (
                "\n\nDeterministic media metadata: "
                f"duration={metadata.duration:.3f}s, fps={metadata.fps:.3f}, "
                f"resolution={metadata.width}x{metadata.height}."
            )
        except VideoInspectionError:
            LOGGER.warning("opencv_metadata_unavailable file=%s", path.name)
        try:
            uploaded = self.client.files.upload(file=str(path))
            uploaded = self._wait_until_ready(uploaded)
            response = self._generate_content(uploaded, prompt, VideoAnalysis)
            analysis = parse_model_response(response, VideoAnalysis)
            if metadata is not None:
                normalized_events = []
                for event in analysis.events:
                    if event.timestamp <= metadata.duration + 1:
                        normalized_events.append(
                            event.model_copy(
                                update={"timestamp": min(event.timestamp, metadata.duration)}
                            )
                        )
                    else:
                        LOGGER.warning(
                            "event_outside_video file=%s timestamp=%.3f",
                            path.name,
                            event.timestamp,
                        )
                analysis = VideoAnalysis(events=normalized_events)
            LOGGER.info(
                "video_analysis_complete file=%s events=%d duration_seconds=%.3f",
                path.name,
                len(analysis.events),
                time.monotonic() - started,
            )
            return analysis
        except VideoAnalysisError:
            raise
        except AIResponseError as error:
            raise VideoAnalysisError(str(error)) from error
        except Exception as error:
            LOGGER.exception("video_analysis_failed file=%s", path.name)
            raise VideoAnalysisError(f"Gemini could not analyze {path.name}: {error}") from error
        finally:
            if uploaded is not None and getattr(uploaded, "name", None):
                try:
                    self.client.files.delete(name=uploaded.name)
                except Exception:
                    LOGGER.warning("gemini_file_cleanup_failed name=%s", uploaded.name)


def analyze_video(
    video_path: str | Path, api_key: str, model: str | None = None
) -> VideoAnalysis:
    return GeminiVideoAnalyzer(api_key, model).analyze_video(video_path)
