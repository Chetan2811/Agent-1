"""Shared defensive parsing for structured Gemini responses."""

from __future__ import annotations

import json
from typing import TypeVar

from pydantic import BaseModel, ValidationError

T = TypeVar("T", bound=BaseModel)


class AIResponseError(RuntimeError):
    """Raised when an AI response cannot cross the validation boundary."""


def parse_model_response(response: object, model_type: type[T]) -> T:
    parsed = getattr(response, "parsed", None)
    if isinstance(parsed, model_type):
        return parsed
    if parsed is not None:
        try:
            return model_type.model_validate(parsed)
        except ValidationError as error:
            raise AIResponseError(f"AI response failed schema validation: {error}") from error

    text = (getattr(response, "text", None) or "").strip()
    if not text:
        raise AIResponseError("Gemini returned an empty response.")
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as error:
        raise AIResponseError("Gemini returned malformed JSON.") from error
    try:
        return model_type.model_validate(payload)
    except ValidationError as error:
        raise AIResponseError(f"AI response failed schema validation: {error}") from error
