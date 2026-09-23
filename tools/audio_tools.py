"""Safe FFmpeg-based audio mixing and loudness normalization."""

from __future__ import annotations

from pathlib import Path

from .video_tools import _output, _run, probe_video


def mix_music(
    video_path: str | Path,
    music_path: str | Path,
    output_path: str | Path,
    music_volume: float = 0.25,
    game_volume: float = 1,
) -> Path:
    if not 0 <= music_volume <= 1 or not 0 <= game_volume <= 2:
        raise ValueError("Audio volumes are outside the supported range.")
    output = _output(output_path)
    has_audio = bool(probe_video(video_path)["has_audio"])
    command = [
        "ffmpeg",
        "-nostdin",
        "-y",
        "-i",
        str(video_path),
        "-stream_loop",
        "-1",
        "-i",
        str(music_path),
    ]
    if has_audio:
        filters = (
            f"[0:a]volume={game_volume:.6g}[game];[1:a]volume={music_volume:.6g}[music];"
            "[game][music]amix=inputs=2:duration=first:dropout_transition=2[aout]"
        )
    else:
        filters = f"[1:a]volume={music_volume:.6g}[aout]"
    command.extend(
        [
            "-filter_complex",
            filters,
            "-map",
            "0:v:0",
            "-map",
            "[aout]",
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-shortest",
            "-movflags",
            "+faststart",
            str(output),
        ]
    )
    _run(command, "mix_music")
    return output


def normalize_audio(
    video_path: str | Path, output_path: str | Path, target_lufs: float = -14
) -> Path:
    if not -24 <= target_lufs <= -8:
        raise ValueError("target_lufs must be between -24 and -8")
    output = _output(output_path)
    media = probe_video(video_path)
    command = ["ffmpeg", "-nostdin", "-y", "-i", str(video_path)]
    if media["has_audio"]:
        command.extend(
            [
                "-af",
                f"loudnorm=I={target_lufs}:TP=-1.5:LRA=11",
                "-c:v",
                "copy",
                "-c:a",
                "aac",
                "-b:a",
                "192k",
            ]
        )
    else:
        command.extend(["-c", "copy"])
    command.extend(["-movflags", "+faststart", str(output)])
    _run(command, "normalize_audio")
    return output
