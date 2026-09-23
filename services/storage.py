"""Local storage abstraction with filename and size validation."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import BinaryIO
from uuid import uuid4

VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v"}
AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg"}


def safe_filename(name: str) -> str:
    original = Path(name).name
    stem = re.sub(r"[^A-Za-z0-9._-]+", "_", Path(original).stem).strip("._") or "upload"
    suffix = re.sub(r"[^A-Za-z0-9.]", "", Path(original).suffix.lower())
    return f"{stem[:100]}{suffix}"


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class LocalStorage:
    def __init__(self, upload_dir: Path, output_dir: Path, max_upload_mb: int = 300) -> None:
        self.upload_dir = upload_dir
        self.output_dir = output_dir
        self.max_bytes = max_upload_mb * 1024 * 1024
        self.upload_dir.mkdir(parents=True, exist_ok=True)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def save_upload(self, name: str, data: bytes | BinaryIO, *, media_type: str = "video") -> Path:
        filename = safe_filename(name)
        allowed = VIDEO_EXTENSIONS if media_type == "video" else AUDIO_EXTENSIONS
        if Path(filename).suffix not in allowed:
            raise ValueError(
                f"Unsupported {media_type} file type: {Path(filename).suffix or 'none'}"
            )
        payload = data.read() if hasattr(data, "read") else data
        if not isinstance(payload, bytes):
            raise TypeError("Upload content must be bytes or a binary stream.")
        if not payload or len(payload) > self.max_bytes:
            raise ValueError(
                f"Upload must be between 1 byte and {self.max_bytes // (1024 * 1024)} MB."
            )
        destination = self.upload_dir / f"{uuid4().hex[:12]}_{filename}"
        destination.write_bytes(payload)
        return destination

    def output_path(self, job_id: str) -> Path:
        if not re.fullmatch(r"[A-Za-z0-9_-]+", job_id):
            raise ValueError("Invalid job identifier.")
        return self.output_dir / f"montage_{job_id}.mp4"
