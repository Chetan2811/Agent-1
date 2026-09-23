"""Approved FFmpeg tools. Commands are constructed only by trusted Python code."""

from __future__ import annotations

import json
import logging
import math
import subprocess
from pathlib import Path

LOGGER = logging.getLogger(__name__)
TRANSITIONS = {"fade", "fadeblack", "dissolve", "wipeleft", "slideright"}


class VideoToolError(RuntimeError):
    pass


def _output(path: str | Path) -> Path:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        raise VideoToolError(f"Refusing to overwrite existing artifact: {output.name}")
    return output


def _run(command: list[str], operation: str) -> None:
    LOGGER.info("ffmpeg_operation_start operation=%s", operation)
    try:
        subprocess.run(command, check=True, capture_output=True, text=True)
    except FileNotFoundError as error:
        raise VideoToolError(f"{command[0]} is not installed or not on PATH.") from error
    except subprocess.CalledProcessError as error:
        details = (error.stderr or error.stdout or "").strip().splitlines()
        tail = "\n".join(details[-20:])
        raise VideoToolError(f"{operation} failed (exit {error.returncode}).\n{tail}") from error
    LOGGER.info("ffmpeg_operation_complete operation=%s", operation)


def probe_video(path: str | Path) -> dict[str, object]:
    video = Path(path)
    if not video.is_file():
        raise VideoToolError(f"Media file was not found: {video}")
    command = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration:stream=codec_type,width,height,r_frame_rate",
        "-of",
        "json",
        str(video),
    ]
    try:
        result = subprocess.run(command, check=True, capture_output=True, text=True)
        data = json.loads(result.stdout)
        duration = float(data["format"]["duration"])
    except (
        FileNotFoundError,
        subprocess.CalledProcessError,
        KeyError,
        ValueError,
        json.JSONDecodeError,
    ) as error:
        raise VideoToolError(f"Could not inspect media file: {video.name}") from error
    video_stream = next(
        (item for item in data.get("streams", []) if item.get("codec_type") == "video"), {}
    )
    return {
        "duration": duration,
        "has_audio": any(item.get("codec_type") == "audio" for item in data.get("streams", [])),
        "width": int(video_stream.get("width", 0)),
        "height": int(video_stream.get("height", 0)),
        "frame_rate": video_stream.get("r_frame_rate", "0/1"),
    }


def trim_video(input_path: str | Path, output_path: str | Path, start: float, end: float) -> Path:
    if not math.isfinite(start) or not math.isfinite(end) or start < 0 or end <= start:
        raise ValueError("Trim requires finite values with start >= 0 and end > start.")
    output = _output(output_path)
    command = [
        "ffmpeg",
        "-nostdin",
        "-y",
        "-ss",
        f"{start:.6f}",
        "-i",
        str(input_path),
        "-t",
        f"{end - start:.6f}",
        "-map",
        "0:v:0",
        "-map",
        "0:a?",
        "-c:v",
        "libx264",
        "-preset",
        "fast",
        "-crf",
        "20",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-movflags",
        "+faststart",
        str(output),
    ]
    _run(command, "trim")
    return output


def _atempo_chain(speed: float) -> str:
    filters: list[str] = []
    remaining = speed
    while remaining > 2:
        filters.append("atempo=2")
        remaining /= 2
    while remaining < 0.5:
        filters.append("atempo=0.5")
        remaining /= 0.5
    filters.append(f"atempo={remaining:.8g}")
    return ",".join(filters)


def change_speed(
    input_path: str | Path,
    output_path: str | Path,
    speed: float,
    start: float = 0,
    end: float | None = None,
) -> Path:
    if not math.isfinite(speed) or speed <= 0 or speed > 4:
        raise ValueError("Speed must be greater than zero and at most 4.")
    media = probe_video(input_path)
    duration = float(media["duration"])
    range_end = duration if end is None else end
    if start < 0 or range_end <= start or range_end > duration + 0.1:
        raise ValueError("Speed range must fall within the current clip.")
    output = _output(output_path)
    whole_clip = start <= 0.001 and range_end >= duration - 0.1
    command = ["ffmpeg", "-nostdin", "-y", "-i", str(input_path)]
    if whole_clip:
        command.extend(["-filter:v", f"setpts=PTS/{speed:.8g}"])
        if media["has_audio"]:
            command.extend(["-filter:a", _atempo_chain(speed), "-c:a", "aac", "-b:a", "192k"])
    else:
        ranges = [(0.0, start, 1.0), (start, range_end, speed), (range_end, duration, 1.0)]
        ranges = [item for item in ranges if item[1] - item[0] > 0.001]
        filters: list[str] = []
        concat_inputs: list[str] = []
        for index, (segment_start, segment_end, segment_speed) in enumerate(ranges):
            filters.append(
                f"[0:v]trim=start={segment_start:.6f}:end={segment_end:.6f},"
                f"setpts=(PTS-STARTPTS)/{segment_speed:.8g}[v{index}]"
            )
            concat_inputs.append(f"[v{index}]")
            if media["has_audio"]:
                filters.append(
                    f"[0:a]atrim=start={segment_start:.6f}:end={segment_end:.6f},"
                    f"asetpts=PTS-STARTPTS,{_atempo_chain(segment_speed)}[a{index}]"
                )
                concat_inputs.append(f"[a{index}]")
        filters.append(
            "".join(concat_inputs)
            + f"concat=n={len(ranges)}:v=1:a={int(bool(media['has_audio']))}[vout]"
            + ("[aout]" if media["has_audio"] else "")
        )
        command.extend(["-filter_complex", ";".join(filters), "-map", "[vout]"])
        if media["has_audio"]:
            command.extend(["-map", "[aout]", "-c:a", "aac", "-b:a", "192k"])
    command.extend(
        [
            "-c:v",
            "libx264",
            "-preset",
            "fast",
            "-crf",
            "20",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            str(output),
        ]
    )
    _run(command, "speed_change")
    return output


def slow_motion(
    input_path: str | Path,
    output_path: str | Path,
    speed: float,
    start: float = 0,
    end: float | None = None,
) -> Path:
    if speed >= 1:
        raise ValueError("Slow motion speed must be less than 1.")
    return change_speed(input_path, output_path, speed, start, end)


def concat_clips(
    input_paths: list[str | Path],
    output_path: str | Path,
    transition: str = "fade",
    transition_duration: float = 0.25,
) -> Path:
    if len(input_paths) < 2:
        raise ValueError("Concat requires at least two clips.")
    if transition not in TRANSITIONS:
        raise ValueError(f"Unsupported transition: {transition}")
    if not 0.05 <= transition_duration <= 2:
        raise ValueError("Transition duration must be between 0.05 and 2 seconds.")
    paths = [Path(path) for path in input_paths]
    media = [probe_video(path) for path in paths]
    use_audio = all(bool(item["has_audio"]) for item in media)
    output = _output(output_path)
    command = ["ffmpeg", "-nostdin", "-y"]
    for path in paths:
        command.extend(["-i", str(path)])

    filters: list[str] = []
    for index in range(len(paths)):
        filters.append(
            f"[{index}:v]scale=1280:720:force_original_aspect_ratio=decrease,"
            f"pad=1280:720:(ow-iw)/2:(oh-ih)/2,fps=30,format=yuv420p,setsar=1,settb=AVTB[v{index}n]"
        )
        if use_audio:
            filters.append(f"[{index}:a]aresample=48000,asetpts=PTS-STARTPTS[a{index}n]")
    video_label = "v0n"
    audio_label = "a0n"
    combined_duration = float(media[0]["duration"])
    for index in range(1, len(paths)):
        effect_duration = min(
            transition_duration, combined_duration / 2, float(media[index]["duration"]) / 2
        )
        offset = combined_duration - effect_duration
        filters.append(
            f"[{video_label}][v{index}n]xfade=transition={transition}:duration={effect_duration:.6f}:offset={offset:.6f}[vx{index}]"
        )
        video_label = f"vx{index}"
        if use_audio:
            filters.append(
                f"[{audio_label}][a{index}n]acrossfade=d={effect_duration:.6f}[ax{index}]"
            )
            audio_label = f"ax{index}"
        combined_duration += float(media[index]["duration"]) - effect_duration
    command.extend(["-filter_complex", ";".join(filters), "-map", f"[{video_label}]"])
    if use_audio:
        command.extend(["-map", f"[{audio_label}]", "-c:a", "aac", "-b:a", "192k"])
    command.extend(
        [
            "-c:v",
            "libx264",
            "-preset",
            "fast",
            "-crf",
            "20",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            str(output),
        ]
    )
    _run(command, "concat_with_transition")
    return output


def add_transition(input_path: str | Path, output_path: str | Path, duration: float = 0.4) -> Path:
    media = probe_video(input_path)
    clip_duration = float(media["duration"])
    fade_duration = min(duration, clip_duration / 2)
    if fade_duration <= 0:
        raise ValueError("Fade duration must be positive.")
    output = _output(output_path)
    video_fades = (
        f"fade=t=in:st=0:d={fade_duration:.6f},"
        f"fade=t=out:st={clip_duration - fade_duration:.6f}:d={fade_duration:.6f}"
    )
    command = [
        "ffmpeg",
        "-nostdin",
        "-y",
        "-i",
        str(input_path),
        "-vf",
        video_fades,
    ]
    if media["has_audio"]:
        audio_fades = (
            f"afade=t=in:st=0:d={fade_duration:.6f},"
            f"afade=t=out:st={clip_duration - fade_duration:.6f}:d={fade_duration:.6f}"
        )
        command.extend(
            [
                "-af",
                audio_fades,
                "-c:a",
                "aac",
                "-b:a",
                "192k",
            ]
        )
    command.extend(
        [
            "-c:v",
            "libx264",
            "-preset",
            "fast",
            "-crf",
            "20",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            str(output),
        ]
    )
    _run(command, "fade_in_out")
    return output
