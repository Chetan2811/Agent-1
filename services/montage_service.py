"""Reusable orchestration for Streamlit, FastAPI, and tests."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable
from uuid import uuid4

from ai.edit_planner import EditingPlanner
from ai.video_analyzer import GeminiVideoAnalyzer
from config import Settings, get_settings
from plan_executor import execute_plan
from schemas import EditPlan, VideoAnalysis, VideoEvent

from .persistence import JobRepository
from .storage import LocalStorage, sha256_file

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class MontageResult:
    job_id: str
    analysis: VideoAnalysis
    plan: EditPlan
    output_path: Path
    processing_duration: float


def deduplicate_events(events: Iterable[VideoEvent], tolerance: float = 1.0) -> list[VideoEvent]:
    """Deduplicate same-type, same-source events within a timestamp tolerance."""
    if tolerance < 0:
        raise ValueError("tolerance must be non-negative")
    kept: list[VideoEvent] = []
    for event in sorted(events, key=lambda item: (item.source or "", item.type, item.timestamp)):
        duplicate_index = next(
            (
                index
                for index, prior in enumerate(kept)
                if prior.type == event.type
                and prior.source == event.source
                and abs(prior.timestamp - event.timestamp) <= tolerance
            ),
            None,
        )
        if duplicate_index is None:
            kept.append(event)
        else:
            prior = kept[duplicate_index]
            if (event.confidence or -1) > (prior.confidence or -1):
                kept[duplicate_index] = event
    return sorted(kept, key=lambda item: (item.source or "", item.timestamp))


class MontageService:
    def __init__(
        self,
        settings: Settings | None = None,
        *,
        analyzer: GeminiVideoAnalyzer | None = None,
        planner: EditingPlanner | None = None,
        repository: JobRepository | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.storage = LocalStorage(
            self.settings.upload_dir, self.settings.output_dir, self.settings.max_upload_mb
        )
        self.settings.temp_dir.mkdir(parents=True, exist_ok=True)
        self.repository = repository or JobRepository(self.settings.database_url)
        self.analyzer = analyzer
        self.planner = planner

    def _analyzer(self) -> GeminiVideoAnalyzer:
        return self.analyzer or GeminiVideoAnalyzer(
            self.settings.gemini_api_key or "", self.settings.gemini_model
        )

    def _planner(self) -> EditingPlanner:
        return self.planner or EditingPlanner(
            self.settings.gemini_api_key or "", self.settings.gemini_model
        )

    def _cache_path(self, video: Path) -> Path:
        key = f"{sha256_file(video)}_{self.settings.gemini_model}".encode()
        import hashlib

        return self.settings.temp_dir / "analysis_cache" / f"{hashlib.sha256(key).hexdigest()}.json"

    def analyze(
        self, video_paths: Iterable[str | Path], *, use_cache: bool = True
    ) -> VideoAnalysis:
        all_events: list[VideoEvent] = []
        analyzer: GeminiVideoAnalyzer | None = None
        for value in video_paths:
            path = Path(value)
            cache_path = self._cache_path(path)
            analysis: VideoAnalysis
            if use_cache and cache_path.is_file():
                analysis = VideoAnalysis.model_validate_json(cache_path.read_text())
                LOGGER.info("analysis_cache_hit file=%s", path.name)
            else:
                analyzer = analyzer or self._analyzer()
                analysis = analyzer.analyze_video(path)
                cache_path.parent.mkdir(parents=True, exist_ok=True)
                cache_path.write_text(analysis.model_dump_json(indent=2))
            for event in analysis.events:
                all_events.append(event.model_copy(update={"source": path.name}))
        return VideoAnalysis(events=deduplicate_events(all_events))

    def plan(self, user_request: str, analysis: VideoAnalysis) -> EditPlan:
        return self._planner().create_plan(user_request, analysis)

    def render(
        self,
        plan: EditPlan,
        video_paths: Iterable[str | Path],
        *,
        job_id: str | None = None,
        music_path: str | Path | None = None,
        music_volume: float = 0.25,
        progress: Callable[[str], None] | None = None,
    ) -> Path:
        paths = [Path(path) for path in video_paths]
        identifier = job_id or uuid4().hex[:12]
        sources = {path.name: path for path in paths}
        return execute_plan(
            plan,
            sources,
            self.storage.output_path(identifier),
            temp_root=self.settings.temp_dir,
            music_path=music_path,
            music_volume=music_volume,
            progress=progress,
        )

    def process(
        self,
        video_paths: Iterable[str | Path],
        user_request: str,
        *,
        music_path: str | Path | None = None,
        progress: Callable[[str], None] | None = None,
    ) -> MontageResult:
        paths = [Path(path) for path in video_paths]
        if not paths:
            raise ValueError("At least one video is required.")
        job_id = uuid4().hex[:12]
        self.repository.create(job_id, ", ".join(path.name for path in paths))
        started = time.monotonic()
        try:
            self.repository.update(job_id, status="analyzing")
            analysis = self.analyze(paths)
            self.repository.update(job_id, status="planning", event_count=len(analysis.events))
            plan = self.plan(user_request, analysis)
            self.repository.update(job_id, status="rendering")
            output = self.render(
                plan, paths, job_id=job_id, music_path=music_path, progress=progress
            )
            elapsed = time.monotonic() - started
            self.repository.update(
                job_id,
                status="complete",
                processing_duration=elapsed,
                output_location=str(output),
            )
            return MontageResult(job_id, analysis, plan, output, elapsed)
        except Exception as error:
            self.repository.update(
                job_id,
                status="failed",
                processing_duration=time.monotonic() - started,
                error=str(error)[:2000],
            )
            LOGGER.exception("montage_job_failed job_id=%s", job_id)
            raise
