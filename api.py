"""Optional FastAPI interface reusing the same application service."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from pydantic import BaseModel

from config import get_settings
from schemas import EditPlan, VideoAnalysis
from services.montage_service import MontageService

app = FastAPI(title="Valorant Montage Maker API", version="1.0.0")
service = MontageService(get_settings())


class PlanRequest(BaseModel):
    user_request: str
    analysis: VideoAnalysis


class RenderRequest(BaseModel):
    plan: EditPlan
    video_tokens: list[str]
    music_token: str | None = None
    music_volume: float = 0.25


def _stored_file(token: str) -> Path:
    if Path(token).name != token:
        raise HTTPException(status_code=400, detail="Invalid storage token.")
    path = service.settings.upload_dir / token
    if not path.is_file():
        raise HTTPException(status_code=404, detail=f"Upload not found: {token}")
    return path


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/analyze")
async def analyze(file: UploadFile = File(...)) -> dict[str, object]:
    try:
        path = service.storage.save_upload(file.filename or "upload.mp4", await file.read())
        analysis = service.analyze([path])
        return {"video_token": path.name, "analysis": analysis.model_dump(mode="json")}
    except Exception as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@app.post("/plan", response_model=EditPlan)
def plan(request: PlanRequest) -> EditPlan:
    try:
        return service.plan(request.user_request, request.analysis)
    except Exception as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@app.post("/render")
def render(request: RenderRequest) -> dict[str, str]:
    try:
        videos = [_stored_file(token) for token in request.video_tokens]
        music = _stored_file(request.music_token) if request.music_token else None
        output = service.render(
            request.plan,
            videos,
            music_path=music,
            music_volume=request.music_volume,
        )
        return {"output": output.name}
    except HTTPException:
        raise
    except Exception as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
