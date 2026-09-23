"""Streamlit interface for the validated montage pipeline."""

from __future__ import annotations

import hashlib
import logging
import mimetypes
import os
from dataclasses import replace
from pathlib import Path

import streamlit as st

from config import get_settings
from schemas import EditPlan, VideoAnalysis
from services.montage_service import MontageService

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
VIDEO_TYPES = ["mp4", "mov", "avi", "mkv", "webm", "m4v"]
AUDIO_TYPES = ["mp3", "wav", "m4a", "aac", "flac", "ogg"]


def api_key() -> str | None:
    value = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if value:
        return value
    try:
        return st.secrets.get("GEMINI_API_KEY") or st.secrets.get("GOOGLE_API_KEY")
    except (FileNotFoundError, KeyError):
        return None


@st.cache_resource
def service_for(key: str | None) -> MontageService:
    settings = replace(get_settings(), gemini_api_key=key)
    return MontageService(settings)


def save_videos(service: MontageService, uploads: list[object]) -> list[Path]:
    signatures = [hashlib.sha256(upload.getvalue()).hexdigest() for upload in uploads]
    if signatures != st.session_state.get("video_signatures"):
        paths = [
            service.storage.save_upload(upload.name, upload.getvalue(), media_type="video")
            for upload in uploads
        ]
        st.session_state["video_signatures"] = signatures
        st.session_state["video_paths"] = [str(path) for path in paths]
        for key in ("analysis", "plan", "output_path"):
            st.session_state.pop(key, None)
    return [Path(path) for path in st.session_state["video_paths"]]


def save_music(service: MontageService, upload: object | None) -> Path | None:
    if upload is None:
        st.session_state.pop("music_signature", None)
        st.session_state.pop("music_path", None)
        return None
    signature = hashlib.sha256(upload.getvalue()).hexdigest()
    if signature != st.session_state.get("music_signature"):
        path = service.storage.save_upload(upload.name, upload.getvalue(), media_type="audio")
        st.session_state["music_signature"] = signature
        st.session_state["music_path"] = str(path)
        st.session_state.pop("output_path", None)
    return Path(st.session_state["music_path"])


st.set_page_config(page_title="Valorant Montage Maker", page_icon="🎬", layout="wide")
st.title("Valorant Montage Maker")
st.caption(
    "Gemini understands gameplay and plans edits; validated Python tools render them with FFmpeg."
)

service = service_for(api_key())
uploads = st.file_uploader(
    "Upload one or more Valorant gameplay videos",
    type=VIDEO_TYPES,
    accept_multiple_files=True,
)
music_upload = st.file_uploader("Optional background music", type=AUDIO_TYPES)
request = st.text_area(
    "Describe your montage",
    placeholder=(
        "Find my best kills, include 3 seconds before and 2 seconds after each kill, "
        "slow down headshots, and add transitions."
    ),
    height=120,
)
music_volume = st.slider("Music volume", 0.0, 1.0, 0.25, 0.05, disabled=music_upload is None)

video_paths: list[Path] = []
music_path: Path | None = None
if uploads:
    try:
        video_paths = save_videos(service, uploads)
        music_path = save_music(service, music_upload)
    except (ValueError, OSError) as error:
        st.error(str(error))

if st.button(
    "Analyze & generate plan", type="primary", disabled=not uploads or not request.strip()
):
    if not api_key():
        st.error("Gemini credentials are missing. Set GEMINI_API_KEY and restart the app.")
    else:
        try:
            with st.status("Building montage plan", expanded=True) as status:
                st.write("Uploading video and analyzing gameplay…")
                analysis = service.analyze(video_paths)
                st.session_state["analysis"] = analysis.model_dump(mode="json")
                st.write(f"Detected {len(analysis.events)} gameplay event(s).")
                st.write("Planning validated edits…")
                plan = service.plan(request, analysis)
                st.session_state["plan"] = plan.model_dump(mode="json")
                st.session_state.pop("output_path", None)
                status.update(label="Analysis and plan complete", state="complete")
        except Exception as error:
            st.error(str(error))

if "analysis" in st.session_state:
    analysis = VideoAnalysis.model_validate(st.session_state["analysis"])
    st.subheader("Detected gameplay events")
    if analysis.events:
        st.dataframe([event.model_dump() for event in analysis.events], use_container_width=True)
    else:
        st.info("No supported gameplay events were detected.")

if "plan" in st.session_state:
    plan = EditPlan.model_validate(st.session_state["plan"])
    st.subheader("Validated edit plan")
    st.json(plan.model_dump(mode="json"))
    if st.button("Run montage", type="primary"):
        stage = st.empty()
        try:
            output = service.render(
                plan,
                video_paths,
                music_path=music_path,
                music_volume=music_volume,
                progress=lambda message: stage.info(message),
            )
            st.session_state["output_path"] = str(output)
            stage.success("Montage complete")
        except Exception as error:
            stage.empty()
            st.error(str(error))

if "output_path" in st.session_state:
    output_path = Path(st.session_state["output_path"])
    if output_path.is_file():
        st.subheader("Final montage")
        st.video(str(output_path))
        st.download_button(
            "Download montage",
            output_path.read_bytes(),
            file_name=output_path.name,
            mime=mimetypes.guess_type(output_path.name)[0] or "video/mp4",
        )
    else:
        st.warning("The rendered output is no longer available.")
