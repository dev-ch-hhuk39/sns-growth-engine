"""Fail-closed inspection of local video files and persisted evidence."""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any


def _positive_int(value: Any) -> int:
    try:
        return max(0, int(float(value or 0)))
    except (TypeError, ValueError):
        return 0


def _positive_float(value: Any) -> float:
    try:
        return max(0.0, float(value or 0))
    except (TypeError, ValueError):
        return 0.0


def _aspect_ratio(width: int, height: int) -> str:
    if width <= 0 or height <= 0:
        return ""

    if width * 16 == height * 9:
        return "9:16"

    if width * 9 == height * 16:
        return "16:9"

    if width == height:
        return "1:1"

    return f"{width}:{height}"


def asset_has_video_evidence(
    asset: dict[str, Any],
) -> bool:
    """Require persisted proof of a playable audiovisual clip."""

    status = str(
        asset.get("media_probe_status", "")
    ).strip().upper()

    return (
        status == "PASS"
        and _positive_int(
            asset.get("video_stream_count")
        )
        >= 1
        and _positive_int(
            asset.get("audio_stream_count")
        )
        >= 1
        and _positive_int(asset.get("width")) > 0
        and _positive_int(asset.get("height")) > 0
    )


def probe_video_file(
    path: str | Path,
    *,
    timeout_seconds: int = 30,
) -> dict[str, Any]:
    """Inspect a local media file with ffprobe and fail closed."""

    candidate = Path(path)

    base = {
        "media_probe_status": "BLOCKED",
        "media_probe_reason": "",
        "video_stream_count": 0,
        "audio_stream_count": 0,
        "width": 0,
        "height": 0,
        "duration_seconds": 0.0,
        "aspect_ratio": "",
    }

    if not candidate.is_file():
        return {
            **base,
            "media_probe_reason": "local_media_file_missing",
        }

    if candidate.stat().st_size <= 0:
        return {
            **base,
            "media_probe_reason": "local_media_file_empty",
        }

    ffprobe = shutil.which("ffprobe")

    if not ffprobe:
        return {
            **base,
            "media_probe_reason": "ffprobe_not_installed",
        }

    try:
        completed = subprocess.run(
            [
                ffprobe,
                "-v",
                "error",
                "-show_streams",
                "-show_format",
                "-of",
                "json",
                str(candidate),
            ],
            text=True,
            capture_output=True,
            timeout=max(5, min(timeout_seconds, 60)),
            check=False,
        )
    except (
        OSError,
        subprocess.TimeoutExpired,
    ) as exc:
        return {
            **base,
            "media_probe_reason": (
                f"{type(exc).__name__}:ffprobe_failed"
            ),
        }

    if completed.returncode != 0:
        return {
            **base,
            "media_probe_reason": "ffprobe_failed",
        }

    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError:
        return {
            **base,
            "media_probe_reason": (
                "ffprobe_invalid_json"
            ),
        }

    streams = payload.get("streams", [])

    video_streams = [
        stream
        for stream in streams
        if (
            stream.get("codec_type") == "video"
            and not bool(
                (
                    stream.get("disposition")
                    or {}
                ).get("attached_pic")
            )
        )
    ]

    audio_streams = [
        stream
        for stream in streams
        if stream.get("codec_type") == "audio"
    ]

    width = max(
        (
            _positive_int(stream.get("width"))
            for stream in video_streams
        ),
        default=0,
    )

    height = max(
        (
            _positive_int(stream.get("height"))
            for stream in video_streams
        ),
        default=0,
    )

    duration = _positive_float(
        (payload.get("format") or {}).get(
            "duration"
        )
    )

    if duration <= 0:
        duration = max(
            (
                _positive_float(
                    stream.get("duration")
                )
                for stream in streams
            ),
            default=0.0,
        )

    reasons: list[str] = []

    if not video_streams:
        reasons.append("video_stream_missing")

    if not audio_streams:
        reasons.append("audio_stream_missing")

    if width <= 0 or height <= 0:
        reasons.append("video_dimensions_missing")

    return {
        "media_probe_status": (
            "PASS"
            if not reasons
            else "BLOCKED"
        ),
        "media_probe_reason": "|".join(
            reasons
        ),
        "video_stream_count": len(
            video_streams
        ),
        "audio_stream_count": len(
            audio_streams
        ),
        "width": width,
        "height": height,
        "duration_seconds": duration,
        "aspect_ratio": _aspect_ratio(
            width,
            height,
        ),
    }
