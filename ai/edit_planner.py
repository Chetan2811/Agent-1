"""Gemini edit planning over validated gameplay events."""

from __future__ import annotations

import logging

from config import DEFAULT_GEMINI_MODEL
from schemas import EditPlan, VideoAnalysis

from .common import AIResponseError, parse_model_response
from .prompts import EDIT_PLANNER_PROMPT

LOGGER = logging.getLogger(__name__)


class EditPlanningError(RuntimeError):
    """Raised when a safe structured plan cannot be produced."""


class EditingPlanner:
    def __init__(
        self, api_key: str, model: str = DEFAULT_GEMINI_MODEL, *, client: object | None = None
    ) -> None:
        if not api_key and client is None:
            raise ValueError("GEMINI_API_KEY is required for edit planning.")
        if client is None:
            try:
                from google import genai
            except ImportError as error:
                raise RuntimeError("Install google-genai to use Gemini planning.") from error
            client = genai.Client(api_key=api_key)
        self.client = client
        self.model = model

    def create_plan(self, user_request: str, analysis: VideoAnalysis) -> EditPlan:
        if not user_request.strip():
            raise ValueError("Enter an editing request first.")
        if not analysis.events:
            raise EditPlanningError(
                "No gameplay events were detected; no montage plan was generated."
            )
        request = (
            f"{EDIT_PLANNER_PROMPT}\n\n"
            f"User request:\n{user_request.strip()}\n\n"
            f"Validated analysis:\n{analysis.model_dump_json()}"
        )
        try:
            response = self.client.models.generate_content(
                model=self.model,
                contents=request,
                config={
                    "response_mime_type": "application/json",
                    "response_json_schema": EditPlan.model_json_schema(),
                    "temperature": 0.1,
                },
            )
            return parse_model_response(response, EditPlan)
        except AIResponseError as error:
            raise EditPlanningError(str(error)) from error
        except Exception as error:
            LOGGER.exception("edit_planning_failed")
            raise EditPlanningError(f"Gemini could not create an edit plan: {error}") from error


def generate_edit_plan(
    user_request: str,
    analysis: VideoAnalysis,
    api_key: str,
    model: str = DEFAULT_GEMINI_MODEL,
) -> EditPlan:
    return EditingPlanner(api_key, model).create_plan(user_request, analysis)
