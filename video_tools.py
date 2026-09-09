"""Predefined video-editing tools used by the plan executor."""

from pathlib import Path
import subprocess


def trim_video(input_path: Path, output_path: Path, start: float, end: float) -> None:
    """Trim a video from ``start`` seconds up to ``end`` seconds."""
    duration = end - start
    if duration <= 0:
        raise ValueError("Trim end must be greater than trim start.")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    command = [
        "ffmpeg", "-y", "-ss", str(start), "-i", str(input_path),
        "-t", str(duration), "-c:v", "libx264", "-c:a", "aac",
        str(output_path),
    ]

    try:
        subprocess.run(command, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as error:
        details = (error.stderr or error.stdout or "").strip()
        message = f"FFmpeg trim failed with exit code {error.returncode}."
        if details:
            message = f"{message}\n{details}"
        raise RuntimeError(message) from error

