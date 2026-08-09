"""Bounded physical materialization of a reviewed clip time range with FFmpeg."""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

MAX_CLIP_SECONDS = 180.0


def parse_timecode(value: Any) -> float:
    raw = str(value or "").strip()
    if not raw:
        raise ValueError("timecode is empty")
    try:
        return float(raw)
    except ValueError:
        pass
    parts = raw.split(":")
    if len(parts) not in {2, 3}:
        raise ValueError(f"invalid timecode: {raw}")
    nums = [float(part) for part in parts]
    if len(nums) == 2:
        return nums[0] * 60.0 + nums[1]
    return nums[0] * 3600.0 + nums[1] * 60.0 + nums[2]


def validate_bounds(start_seconds: float, end_seconds: float) -> float:
    start = float(start_seconds)
    end = float(end_seconds)
    duration = end - start
    if start < 0 or duration <= 0:
        raise ValueError("invalid clip bounds")
    if duration > MAX_CLIP_SECONDS:
        raise ValueError("clip duration exceeds bounded maximum")
    return duration


def build_ffmpeg_command(
    input_path: str | Path,
    output_path: str | Path,
    start_seconds: float,
    end_seconds: float,
    *,
    ffmpeg_bin: str = "ffmpeg",
) -> list[str]:
    duration = validate_bounds(start_seconds, end_seconds)
    return [
        ffmpeg_bin,
        "-hide_banner",
        "-loglevel",
        "error",
        "-nostdin",
        "-n",
        "-i",
        str(input_path),
        "-ss",
        f"{float(start_seconds):.3f}",
        "-t",
        f"{duration:.3f}",
        "-map",
        "0:v:0",
        "-map",
        "0:a:0?",
        "-c:v",
        "libx264",
        "-preset",
        "fast",
        "-crf",
        "20",
        "-c:a",
        "aac",
        "-movflags",
        "+faststart",
        str(output_path),
    ]


def probe_media_streams(path: str | Path, *, ffprobe_bin: str = "ffprobe") -> dict[str, Any]:
    proc = subprocess.run(
        [ffprobe_bin, "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)],
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(proc.stdout or "{}")
    streams = list(payload.get("streams") or [])
    video = []
    audio = []
    for stream in streams:
        codec_type = str(stream.get("codec_type") or "")
        if codec_type == "video":
            attached = int((stream.get("disposition") or {}).get("attached_pic") or 0)
            width = int(stream.get("width") or 0)
            height = int(stream.get("height") or 0)
            if not attached and width > 0 and height > 0:
                video.append(stream)
        elif codec_type == "audio":
            audio.append(stream)
    duration = float((payload.get("format") or {}).get("duration") or 0.0)
    width = max((int(s.get("width") or 0) for s in video), default=0)
    height = max((int(s.get("height") or 0) for s in video), default=0)
    return {
        "video_stream_count": len(video),
        "audio_stream_count": len(audio),
        "width": width,
        "height": height,
        "duration_seconds": duration,
    }


def require_video_stream(path: str | Path, *, ffprobe_bin: str = "ffprobe") -> dict[str, Any]:
    probe = probe_media_streams(path, ffprobe_bin=ffprobe_bin)
    if probe["video_stream_count"] < 1 or probe["width"] <= 0 or probe["height"] <= 0:
        raise RuntimeError("media does not contain a usable visual video stream")
    return probe


def probe_duration(path: str | Path, *, ffprobe_bin: str = "ffprobe") -> float:
    return float(probe_media_streams(path, ffprobe_bin=ffprobe_bin)["duration_seconds"])


def materialize_clip(
    input_path: str | Path,
    output_path: str | Path,
    start_seconds: float,
    end_seconds: float,
) -> dict[str, Any]:
    src = Path(input_path).expanduser().resolve()
    dst = Path(output_path).expanduser().resolve()
    duration = validate_bounds(start_seconds, end_seconds)
    if not src.is_file():
        raise FileNotFoundError("source video file not found")
    if dst.exists():
        raise FileExistsError("output path already exists")
    ffmpeg_bin = shutil.which("ffmpeg")
    ffprobe_bin = shutil.which("ffprobe")
    if not ffmpeg_bin or not ffprobe_bin:
        raise RuntimeError("ffmpeg and ffprobe executables are required")
    source_probe = require_video_stream(src, ffprobe_bin=ffprobe_bin)
    dst.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        build_ffmpeg_command(src, dst, start_seconds, end_seconds, ffmpeg_bin=ffmpeg_bin),
        check=True,
        capture_output=True,
        text=True,
    )
    if not dst.is_file() or dst.stat().st_size <= 0:
        raise RuntimeError("FFmpeg did not produce a non-empty clip")
    output_probe = require_video_stream(dst, ffprobe_bin=ffprobe_bin)
    actual = float(output_probe["duration_seconds"])
    if actual <= 0 or abs(actual - duration) > 2.5:
        raise RuntimeError("materialized clip duration failed validation")
    return {
        "output_path": str(dst),
        "requested_duration_seconds": duration,
        "actual_duration_seconds": actual,
        "size_bytes": dst.stat().st_size,
        "video_stream_count": output_probe["video_stream_count"],
        "audio_stream_count": output_probe["audio_stream_count"],
        "width": output_probe["width"],
        "height": output_probe["height"],
        "source_video_stream_count": source_probe["video_stream_count"],
    }
