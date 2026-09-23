"""One-shot diagnostic for Gemini Files API video understanding.

Usage: python gemini_video_smoke.py path/to/small-video.mp4
"""

from __future__ import annotations

import argparse

from ai.video_analyzer import GeminiVideoAnalyzer
from config import get_settings


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("video", help="Path to one small diagnostic video")
    args = parser.parse_args()
    settings = get_settings()
    analyzer = GeminiVideoAnalyzer(
        settings.gemini_api_key or "",
        settings.gemini_model,
    )
    uploaded = None
    try:
        uploaded = analyzer.client.files.upload(file=args.video)
        uploaded = analyzer._wait_until_ready(uploaded)
        response = analyzer._generate_content(
            uploaded,
            "Describe what happens in this video.",
        )
        print(response.text)
    finally:
        if uploaded is not None and getattr(uploaded, "name", None):
            analyzer.client.files.delete(name=uploaded.name)


if __name__ == "__main__":
    main()
