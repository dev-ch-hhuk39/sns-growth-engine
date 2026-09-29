"""Bounded local/vision understanding for an approved direct-media asset."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

import requests


def _compact(text: str, limit: int) -> str:
    return " ".join(str(text or "").split())[:limit]


def _hash(text: str) -> str:
    return hashlib.sha256(str(text or "").encode("utf-8")).hexdigest() if text else ""


def _file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def provider_failure_class(exc: BaseException) -> str:
    """Classify a vision-provider failure without retaining response bodies."""
    if isinstance(exc, requests.Timeout):
        return "timeout"
    if isinstance(exc, requests.ConnectionError):
        return "network_error"
    if isinstance(exc, requests.HTTPError):
        status = int(getattr(getattr(exc, "response", None), "status_code", 0) or 0)
        if status in {401, 403}:
            return "auth_rejected"
        if status == 429:
            return "rate_limited"
        if status == 404:
            return "model_unavailable"
        if 500 <= status <= 599:
            return "provider_internal_error"
        return "invalid_response"
    if isinstance(exc, (KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError)):
        return "invalid_response"
    return "internal_error"


def _run(command: list[str], timeout: int) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, capture_output=True, text=True, timeout=timeout, check=False)


def _frame_timestamps(duration_seconds: float) -> list[float]:
    if duration_seconds <= 0:
        return [1.0]
    return sorted({round(max(0.0, min(duration_seconds - 0.1, duration_seconds * ratio)), 2) for ratio in (0.15, 0.5, 0.85)})


def representative_frames(video_path: Path, duration_seconds: float, workdir: Path) -> list[tuple[float, Path]]:
    frames: list[tuple[float, Path]] = []
    for index, timestamp in enumerate(_frame_timestamps(duration_seconds)):
        target = workdir / f"frame_{index}.jpg"
        run = _run([
            "ffmpeg", "-nostdin", "-v", "error", "-ss", str(timestamp), "-i", str(video_path),
            "-frames:v", "1", "-vf", "scale='min(960,iw)':-2", "-y", str(target),
        ], timeout=45)
        if run.returncode == 0 and target.exists() and target.stat().st_size:
            frames.append((timestamp, target))
    return frames


def normalized_image(image_path: Path, workdir: Path) -> Path:
    from PIL import Image

    target = workdir / "image.jpg"
    with Image.open(image_path) as image:
        image = image.convert("RGB")
        image.thumbnail((1280, 1280))
        image.save(target, "JPEG", quality=85, optimize=True)
    return target


def ocr_images(paths: list[Path]) -> str:
    if not shutil.which("tesseract"):
        return ""
    parts: list[str] = []
    for path in paths[:4]:
        run = _run(["tesseract", str(path), "stdout", "-l", "jpn+eng"], timeout=60)
        if run.returncode != 0:
            run = _run(["tesseract", str(path), "stdout", "-l", "eng"], timeout=60)
        if run.returncode == 0 and run.stdout.strip():
            parts.append(run.stdout.strip())
    return _compact("\n".join(parts), 12000)


def transcribe_video(path: Path, *, max_seconds: int = 300) -> dict[str, Any]:
    if os.environ.get("ALLOW_LOCAL_TRANSCRIPTION", "").lower() not in {"1", "true", "yes"}:
        return {"status": "DISABLED", "text": "", "provider": "none"}
    try:
        from faster_whisper import WhisperModel

        model = WhisperModel("small", device="cpu", compute_type="int8", cpu_threads=1, num_workers=1)
        segments, info = model.transcribe(
            str(path), beam_size=1, vad_filter=True, language="ja",
            clip_timestamps=f"0,{max_seconds}",
        )
        text = _compact(" ".join(segment.text.strip() for segment in segments if segment.text.strip()), 40000)
        return {
            "status": "PASS" if text else "UNAVAILABLE",
            "text": text,
            "provider": "faster_whisper_small",
            "language": str(getattr(info, "language", "")),
        }
    except (ImportError, RuntimeError, OSError, TypeError, ValueError) as exc:
        return {"status": "UNAVAILABLE", "text": "", "provider": "faster_whisper_small", "reason": type(exc).__name__}


def vision_summary(paths: list[Path], *, media_type: str,
                   source_metadata: dict[str, Any] | None = None,
                   transcript: dict[str, Any] | None = None,
                   account_content_contract: dict[str, Any] | None = None) -> dict[str, Any]:
    # Keep call compatibility, but metadata, transcripts and strategy never enter Vision.
    from media.gemini_vision import GeminiVisionProvider
    return GeminiVisionProvider().understand(paths, media_type=media_type)


def analyze_local_media(path: Path, *, media_type: str, duration_seconds: float = 0,
                        media_asset_id: str = "") -> dict[str, Any]:
    workdir = path.parent / f".understanding_{path.stem}"
    workdir.mkdir(parents=True, exist_ok=True)
    try:
        if media_type == "video":
            frames = representative_frames(path, duration_seconds, workdir)
            images = [frame for _, frame in frames]
            transcript = transcribe_video(path)
        else:
            image = normalized_image(path, workdir)
            frames = [(0.0, image)]
            images = [image]
            transcript = {"status": "NOT_APPLICABLE", "text": "", "provider": "none"}
        ocr = ocr_images(images)
        vision = vision_summary(images, media_type=media_type, transcript=transcript)
        has_asr = bool(transcript.get("text"))
        has_ocr = bool(ocr)
        has_vision = (vision.get("status") == "PASS" and bool(vision.get("visual_facts")))
        content_hash = _file_hash(path)
        evidence_available = bool(has_ocr or has_asr or has_vision)
        if has_vision:
            aggregate = "PASS_VISION"
        elif has_asr:
            aggregate = "PASS_ASR_ONLY"
        elif has_ocr:
            aggregate = "PASS_OCR_ONLY"
        else:
            aggregate = "BLOCKED_NO_EVIDENCE"
        return {
            "status": "PASS" if evidence_available else "BLOCKED",
            "aggregate_status": aggregate,
            "provider": vision.get("provider", "local_media_understanding"),
            "vision_status": vision.get("status", "UNAVAILABLE"),
            "vision_failure_class": vision.get("failure_class", ""),
            "visual_facts": vision.get("visual_facts", []),
            **{key: vision.get(key, "") for key in ("http_status", "model", "response_schema_status", "provider_error_type")},
            "vision_summary_hash": _hash(str(vision.get("visual_summary", ""))),
            "visual_summary": vision.get("visual_summary", ""),
            **{key: vision.get(key, "") for key in (
                "visible_people_or_objects", "visible_action", "key_moment", "main_topic")},
            "visual_evidence": {
                "status": "UNDERSTOOD" if has_vision else "EXTRACTED_ONLY",
                "provider": vision.get("provider", ""),
                "media_asset_id": media_asset_id or f"ma_{content_hash[:24]}",
                "content_hash": content_hash,
                "frame_hashes": [hashlib.sha256(image.read_bytes()).hexdigest() for image in images],
            },
            "visible_text": vision.get("visible_text", ""),
            "main_claims_json": json.dumps(vision.get("main_claims", []), ensure_ascii=False),
            "safety_flags_json": json.dumps(vision.get("safety_flags", []), ensure_ascii=False),
            "ocr_text": ocr,
            "ocr_hash": _hash(ocr),
            "transcript_text": transcript.get("text", ""),
            "transcript_hash": _hash(str(transcript.get("text", ""))),
            "transcription_provider": transcript.get("provider", ""),
            "transcript_status": transcript.get("status", ""),
            "representative_frame_timestamps_json": json.dumps([timestamp for timestamp, _ in frames]),
            "representative_frame_count": str(len(frames)),
            "blocked_reason": "" if evidence_available else "media_understanding_evidence_unavailable",
        }
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
