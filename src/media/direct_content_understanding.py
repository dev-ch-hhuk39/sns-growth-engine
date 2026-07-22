"""Bounded local/vision understanding for an approved direct-media asset."""
from __future__ import annotations

import base64
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

        model = WhisperModel("tiny", device="cpu", compute_type="int8", cpu_threads=1)
        segments, info = model.transcribe(
            str(path), beam_size=1, vad_filter=True, language="ja",
            clip_timestamps=f"0,{max_seconds}",
        )
        text = _compact(" ".join(segment.text.strip() for segment in segments if segment.text.strip()), 40000)
        return {
            "status": "PASS" if text else "UNAVAILABLE",
            "text": text,
            "provider": "faster_whisper_tiny",
            "language": str(getattr(info, "language", "")),
        }
    except (ImportError, RuntimeError, OSError, TypeError, ValueError) as exc:
        return {"status": "UNAVAILABLE", "text": "", "provider": "faster_whisper_tiny", "reason": type(exc).__name__}


def vision_summary(paths: list[Path], *, media_type: str) -> dict[str, Any]:
    token = os.environ.get("GITHUB_TOKEN", "")
    enabled = os.environ.get("GITHUB_MODELS_ENABLED", "").lower() in {"1", "true", "yes"}
    if not token or not enabled or not paths:
        return {"status": "UNAVAILABLE", "visual_summary": "", "visible_text": "", "provider": "github_models_vision"}
    content: list[dict[str, Any]] = [{
        "type": "text",
        "text": (
            "許可済みSNSメディアの内容を日本語で客観的に分析してください。"
            "人物・場面・表示文字・主要テーマだけを記述し、見えない事実や効果を推測しないでください。"
            "JSON keys: visual_summary, visible_text, main_claims, safety_flags。"
        ),
    }]
    for path in paths[:4]:
        encoded = base64.b64encode(path.read_bytes()).decode("ascii")
        content.append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{encoded}", "detail": "low"}})
    payload = {
        "model": os.environ.get("GITHUB_MODELS_VISION_MODEL", "openai/gpt-4.1"),
        "temperature": 0,
        "max_tokens": 700,
        "response_format": {"type": "json_object"},
        "messages": [{"role": "user", "content": content}],
    }
    try:
        response = requests.post(
            os.environ.get("GITHUB_MODELS_ENDPOINT", "https://models.github.ai/inference/chat/completions"),
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {token}",
                "X-GitHub-Api-Version": "2026-03-10",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=75,
        )
        response.raise_for_status()
        raw = str(response.json()["choices"][0]["message"]["content"]).strip()
        raw = raw.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        parsed = json.loads(raw)
        if not isinstance(parsed, dict):
            raise ValueError("vision_result_not_object")
        return {
            "status": "PASS",
            "visual_summary": _compact(parsed.get("visual_summary", ""), 4000),
            "visible_text": _compact(parsed.get("visible_text", ""), 4000),
            "main_claims": [str(value)[:500] for value in parsed.get("main_claims", [])[:20]],
            "safety_flags": [str(value)[:200] for value in parsed.get("safety_flags", [])[:20]],
            "provider": "github_models_vision",
            "media_type": media_type,
        }
    except (requests.RequestException, KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError) as exc:
        return {"status": "UNAVAILABLE", "visual_summary": "", "visible_text": "", "provider": "github_models_vision", "reason": type(exc).__name__}


def analyze_local_media(path: Path, *, media_type: str, duration_seconds: float = 0) -> dict[str, Any]:
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
        vision = vision_summary(images, media_type=media_type)
        evidence_available = bool(ocr or transcript.get("text") or vision.get("visual_summary") or vision.get("visible_text"))
        return {
            "status": "PASS" if evidence_available else "BLOCKED",
            "provider": vision.get("provider", "local_media_understanding"),
            "visual_summary": vision.get("visual_summary", ""),
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
