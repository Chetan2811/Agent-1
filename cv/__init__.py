"""Deterministic OpenCV helpers; semantic event detection remains Gemini's job."""

from .frame_analyzer import VideoMetadata, extract_frame, get_video_metadata, sample_frames

__all__ = ["VideoMetadata", "extract_frame", "get_video_metadata", "sample_frames"]
