"""Lightweight deterministic video inspection and frame extraction."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path


class VideoInspectionError(RuntimeError):
    pass


@dataclass(frozen=True)
class VideoMetadata:
    path: str
    width: int
    height: int
    fps: float
    frame_count: int
    duration: float

    def to_dict(self) -> dict[str, str | int | float]:
        return asdict(self)


def _cv2():
    try:
        import cv2
    except ImportError as error:
        raise VideoInspectionError("Install opencv-python-headless for frame analysis.") from error
    return cv2


def get_video_metadata(path: str | Path) -> VideoMetadata:
    cv2 = _cv2()
    video_path = Path(path)
    if not video_path.is_file():
        raise VideoInspectionError(f"Video was not found: {video_path}")
    capture = cv2.VideoCapture(str(video_path))
    try:
        if not capture.isOpened():
            raise VideoInspectionError(f"OpenCV could not open {video_path.name}.")
        fps = float(capture.get(cv2.CAP_PROP_FPS))
        frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
        width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
        if fps <= 0 or frame_count < 0 or width <= 0 or height <= 0:
            raise VideoInspectionError(f"Invalid video metadata for {video_path.name}.")
        return VideoMetadata(
            path=str(video_path),
            width=width,
            height=height,
            fps=fps,
            frame_count=frame_count,
            duration=frame_count / fps,
        )
    finally:
        capture.release()


def extract_frame(path: str | Path, timestamp: float):
    if timestamp < 0:
        raise ValueError("timestamp must be non-negative")
    cv2 = _cv2()
    capture = cv2.VideoCapture(str(path))
    try:
        if not capture.isOpened():
            raise VideoInspectionError(f"OpenCV could not open {Path(path).name}.")
        capture.set(cv2.CAP_PROP_POS_MSEC, timestamp * 1000)
        ok, frame = capture.read()
        if not ok:
            raise VideoInspectionError(f"Could not read a frame at {timestamp:.3f}s.")
        return frame
    finally:
        capture.release()


def sample_frames(path: str | Path, interval_seconds: float = 5) -> list[tuple[float, object]]:
    if interval_seconds <= 0:
        raise ValueError("interval_seconds must be greater than zero")
    metadata = get_video_metadata(path)
    samples: list[tuple[float, object]] = []
    timestamp = 0.0
    while timestamp < metadata.duration:
        samples.append((timestamp, extract_frame(path, timestamp)))
        timestamp += interval_seconds
    return samples


def event_windows(
    timestamps: list[float],
    duration: float,
    before: float = 3,
    after: float = 2,
) -> list[tuple[float, float]]:
    """Create bounded, merged windows around candidate timestamps."""
    if duration <= 0 or before < 0 or after < 0:
        raise ValueError("duration must be positive and window sizes non-negative")
    windows = sorted((max(0, time - before), min(duration, time + after)) for time in timestamps)
    merged: list[tuple[float, float]] = []
    for start, end in windows:
        if end <= start:
            continue
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged
