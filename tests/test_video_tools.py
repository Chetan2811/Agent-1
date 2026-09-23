import shutil
import subprocess

import pytest

from cv.frame_analyzer import extract_frame, get_video_metadata
from tools.video_tools import concat_clips, probe_video, slow_motion, trim_video

pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="FFmpeg is required")


@pytest.fixture
def tiny_video(tmp_path):
    path = tmp_path / "tiny source.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-nostdin",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=size=320x180:rate=24:duration=3",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=3",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-shortest",
            str(path),
        ],
        check=True,
        capture_output=True,
    )
    return path


def test_trim_supports_paths_with_spaces(tiny_video, tmp_path):
    output = trim_video(tiny_video, tmp_path / "trim result.mp4", 0.5, 1.5)
    assert output.is_file()
    assert float(probe_video(output)["duration"]) == pytest.approx(1, abs=0.2)


def test_concat_creates_real_crossfade(tiny_video, tmp_path):
    first = trim_video(tiny_video, tmp_path / "first.mp4", 0, 1.2)
    second = trim_video(tiny_video, tmp_path / "second.mp4", 1.2, 2.5)
    output = concat_clips([first, second], tmp_path / "joined.mp4", transition_duration=0.1)
    assert output.is_file()
    assert float(probe_video(output)["duration"]) > 2


def test_partial_slow_motion_preserves_video_and_audio(tiny_video, tmp_path):
    output = slow_motion(tiny_video, tmp_path / "slow.mp4", 0.5, start=1, end=2)
    metadata = probe_video(output)
    assert output.is_file()
    assert metadata["has_audio"] is True
    assert float(metadata["duration"]) == pytest.approx(4, abs=0.3)


def test_opencv_metadata_and_frame_extraction(tiny_video):
    metadata = get_video_metadata(tiny_video)
    frame = extract_frame(tiny_video, 1)
    assert metadata.width == 320
    assert metadata.height == 180
    assert metadata.duration == pytest.approx(3, abs=0.2)
    assert frame.shape[:2] == (180, 320)
