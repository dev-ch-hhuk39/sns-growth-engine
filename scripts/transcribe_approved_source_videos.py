#!/usr/bin/env python3
"""Transcribe approved source_videos without exposing transcript text in logs.

The runner is intentionally bounded and permission-gated. It reads individual
video URLs from source_videos, saves transcript_text/segments_json to the
video_transcripts tab, and updates source_videos status. It never posts,
cuts, uploads, or prints transcript bodies.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

from config_loader import get_config  # noqa: E402
from download_approved_media import is_individual_video_url  # noqa: E402
from media.rights_policy import rights_allows_media_use  # noqa: E402
from media_growth_schemas import extract_video_id, redacted_preview  # noqa: E402
from sheets_client import TAB_DEFINITIONS, SheetsClient  # noqa: E402

APPROVED_RIGHTS = {"owned", "licensed", "approved_creator_clip"}
DONE_STATUSES = {"DONE", "FETCHED", "LOCAL_WHISPER_DONE", "YOUTUBE_CAPTIONS_DONE"}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_text(text: str) -> str:
    return hashlib.sha256(str(text or "").encode("utf-8")).hexdigest()


def _true(value: Any) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes"}


def transcript_id_for(video: dict[str, Any]) -> str:
    safe = re.sub(r"[^A-Za-z0-9_]+", "_", str(video.get("source_video_id", "unknown")))[:120]
    return f"tr_{safe}"


def load_sheets() -> SheetsClient:
    cfg = get_config()
    client = SheetsClient(cfg["sheet_id"], cfg["sa_dict"], dry_run=False)
    for logical in ("source_videos", "video_transcripts"):
        client._ensure_tab(logical, TAB_DEFINITIONS[logical])
    return client


def load_rows(client: SheetsClient) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    return (
        [
            dict(r)
            for r in client._call_with_rate_limit_retry(
                "get_all_records:source_videos:transcription",
                lambda: client._ws("source_videos").get_all_records(),
            )
        ],
        [
            dict(r)
            for r in client._call_with_rate_limit_retry(
                "get_all_records:video_transcripts:transcription",
                lambda: client._ws("video_transcripts").get_all_records(),
            )
        ],
    )


def eligible_videos(
    source_videos: list[dict[str, Any]],
    transcripts: list[dict[str, Any]],
    *,
    account_id: str,
    limit: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    existing_done = {
        str(row.get("source_video_id", ""))
        for row in transcripts
        if str(row.get("transcription_status", "")).upper() in DONE_STATUSES and str(row.get("transcript_text", "")).strip()
    }
    selected: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for row in source_videos:
        source_video_id = str(row.get("source_video_id", ""))
        url = str(row.get("canonical_video_url") or row.get("original_video_url") or "")
        rights = str(row.get("rights_status", "")).lower()
        permission = str(row.get("permission_status", "")).lower()
        platform = str(row.get("platform", "")).lower()
        reasons: list[str] = []
        if account_id != "all" and str(row.get("account_id", "")) != account_id:
            reasons.append("account_not_targeted")
        if rights not in APPROVED_RIGHTS or not rights_allows_media_use(rights):
            reasons.append("rights_not_approved")
        if permission != "approved":
            reasons.append("permission_not_approved")
        if platform not in {"youtube", "tiktok"}:
            reasons.append("platform_not_supported")
        if not is_individual_video_url(url):
            reasons.append("individual_video_url_required")
        if not extract_video_id(url, platform):
            reasons.append("video_id_missing")
        if source_video_id in existing_done:
            reasons.append("already_transcribed")
        if reasons:
            skipped.append({"source_video_id": source_video_id, "reason": ",".join(reasons)})
            continue
        selected.append(row)
        if len(selected) >= limit:
            break
    return selected, skipped


def fetch_youtube_captions(video_id: str) -> dict[str, Any]:
    try:
        from youtube_transcript_api import YouTubeTranscriptApi  # type: ignore[import]
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "status": "YOUTUBE_TRANSCRIPT_API_NOT_INSTALLED", "error": type(exc).__name__}
    try:
        try:
            transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
            transcript = None
            for langs in (["ja"], ["en"], ["ja", "en"]):
                try:
                    transcript = transcript_list.find_transcript(langs)
                    break
                except Exception:  # noqa: BLE001
                    continue
            if transcript is None:
                transcript = next(iter(transcript_list))
            raw = transcript.fetch()
            language = getattr(transcript, "language_code", "") or "unknown"
        except AttributeError:
            raw = YouTubeTranscriptApi.get_transcript(video_id, languages=["ja", "en"])
            language = "unknown"
        segments = []
        for item in raw:
            start = float(item.get("start", 0) or 0)
            duration = float(item.get("duration", 0) or 0)
            text = str(item.get("text", "")).strip()
            if not text:
                continue
            segments.append({"start": start, "end": start + duration, "text": text})
        text = "\n".join(seg["text"] for seg in segments)
        if not text.strip():
            return {"ok": False, "status": "EMPTY_CAPTIONS", "error": ""}
        return {"ok": True, "provider": "youtube_transcript_api", "language": language, "text": text, "segments": segments}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "status": "YOUTUBE_CAPTIONS_UNAVAILABLE", "error": type(exc).__name__}


def transcribe_with_local_whisper(video_url: str, *, model_size: str) -> dict[str, Any]:
    if not _true(os.environ.get("ALLOW_LOCAL_TRANSCRIPTION", "false")):
        return {"ok": False, "status": "ALLOW_LOCAL_TRANSCRIPTION_REQUIRED", "error": ""}
    if not _true(os.environ.get("ALLOW_VIDEO_DOWNLOAD", "false")):
        return {"ok": False, "status": "ALLOW_VIDEO_DOWNLOAD_REQUIRED_FOR_TRANSCRIPTION", "error": ""}
    try:
        import yt_dlp  # type: ignore[import]
        from faster_whisper import WhisperModel  # type: ignore[import]
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "status": "LOCAL_WHISPER_NOT_AVAILABLE", "error": type(exc).__name__}
    with TemporaryDirectory(prefix="sns_transcribe_") as tmp:
        outtmpl = str(Path(tmp) / "audio.%(ext)s")
        opts = {
            "format": "bestaudio/best",
            "outtmpl": outtmpl,
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
            "socket_timeout": 30,
        }
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                ydl.download([video_url])
            files = sorted(Path(tmp).glob("audio.*"))
            audio = files[0] if files else None
            if audio is None:
                raise RuntimeError("audio_download_missing")
            model = WhisperModel(model_size, device="cpu", compute_type="int8")
            segments_iter, info = model.transcribe(str(audio), vad_filter=True)
            segments = []
            texts = []
            for seg in segments_iter:
                text = str(getattr(seg, "text", "")).strip()
                if not text:
                    continue
                start = float(getattr(seg, "start", 0.0) or 0.0)
                end = float(getattr(seg, "end", start) or start)
                segments.append({"start": start, "end": end, "text": text})
                texts.append(text)
            full_text = "\n".join(texts)
            if not full_text.strip():
                return {"ok": False, "status": "LOCAL_WHISPER_EMPTY", "error": ""}
            return {
                "ok": True,
                "provider": "local_faster_whisper",
                "language": str(getattr(info, "language", "") or "unknown"),
                "text": full_text,
                "segments": segments,
            }
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "status": "LOCAL_WHISPER_FAILED", "error": type(exc).__name__}


def build_transcript_row(video: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    text = str(result.get("text", ""))
    segments = result.get("segments") or []
    duration = str(video.get("duration_seconds") or "")
    return {
        "transcript_id": transcript_id_for(video),
        "account_id": video.get("account_id", ""),
        "reference_post_id": video.get("source_video_id", ""),
        "source_video_id": video.get("source_video_id", ""),
        "video_id": video.get("video_id", ""),
        "source_id": video.get("source_id", ""),
        "source_platform": video.get("platform", ""),
        "video_url": video.get("canonical_video_url", ""),
        "transcription_provider": result.get("provider", ""),
        "transcription_status": "DONE",
        "duration_seconds": duration,
        "transcript_text": text,
        "segments_json": json.dumps(segments, ensure_ascii=False),
        "language": result.get("language", ""),
        "processed_minutes": round((float(duration or 0) or 0) / 60, 3) if duration else "",
        "transcript_hash": sha256_text(text),
        "chunk_count": len(segments) or max(1, len(text) // 500 + 1),
        "error": "",
        "created_at": now_iso(),
        "updated_at": now_iso(),
    }


def build_unavailable_row(video: dict[str, Any], status: str, error: str) -> dict[str, Any]:
    return {
        "transcript_id": transcript_id_for(video),
        "account_id": video.get("account_id", ""),
        "reference_post_id": video.get("source_video_id", ""),
        "source_video_id": video.get("source_video_id", ""),
        "video_id": video.get("video_id", ""),
        "source_id": video.get("source_id", ""),
        "source_platform": video.get("platform", ""),
        "video_url": video.get("canonical_video_url", ""),
        "transcription_provider": "",
        "transcription_status": status,
        "duration_seconds": video.get("duration_seconds", ""),
        "transcript_text": "",
        "segments_json": "[]",
        "language": "",
        "processed_minutes": "",
        "transcript_hash": "",
        "chunk_count": 0,
        "error": error,
        "created_at": now_iso(),
        "updated_at": now_iso(),
    }


def transcribe_one(video: dict[str, Any], *, model_size: str, allow_local_whisper: bool) -> tuple[dict[str, Any], dict[str, Any]]:
    started = time.monotonic()
    platform = str(video.get("platform", "")).lower()
    url = str(video.get("canonical_video_url") or "")
    video_id = extract_video_id(url, platform)
    result: dict[str, Any] = {"ok": False, "status": "UNAVAILABLE", "error": ""}
    if platform == "youtube" and video_id:
        result = fetch_youtube_captions(video_id)
    if not result.get("ok") and allow_local_whisper:
        result = transcribe_with_local_whisper(url, model_size=model_size)
    if result.get("ok"):
        return build_transcript_row(video, result), {
            "source_video_id": video.get("source_video_id", ""),
            "status": "DONE",
            "provider": result.get("provider", ""),
            "language": result.get("language", ""),
            "chunk_count": len(result.get("segments") or []),
            "preview": redacted_preview(str(result.get("text", "")), 80),
            "processing_seconds": round(time.monotonic() - started, 3),
        }
    status = str(result.get("status") or "UNAVAILABLE")
    return build_unavailable_row(video, status, str(result.get("error", ""))), {
        "source_video_id": video.get("source_video_id", ""),
        "status": status,
        "provider": "",
        "language": "",
        "chunk_count": 0,
        "preview": "",
        "processing_seconds": round(time.monotonic() - started, 3),
    }


def save_rows(client: SheetsClient, transcript_rows: list[dict[str, Any]], source_video_updates: list[dict[str, Any]]) -> dict[str, int]:
    saved = updated = failed = 0
    for row in transcript_rows:
        try:
            if client.save_video_transcript(row):
                saved += 1
        except Exception:
            failed += 1
    for row in source_video_updates:
        try:
            if client.save_source_video(row):
                updated += 1
        except Exception:
            failed += 1
    return {"transcripts_saved": saved, "source_videos_updated": updated, "failed": failed}


def main() -> int:
    parser = argparse.ArgumentParser(description="Transcribe approved source_videos")
    parser.add_argument("--account-id", default="liver_manager", choices=["all", "liver_manager", "night_scout"])
    parser.add_argument("--limit", type=int, default=3)
    parser.add_argument("--model-size", default="tiny")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--use-sheets", action="store_true")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm-transcribe", action="store_true")
    parser.add_argument("--allow-local-whisper", action="store_true")
    args = parser.parse_args()

    blocked = []
    if args.apply and not args.confirm_transcribe:
        blocked.append("--apply requires --confirm-transcribe")
    if args.apply and not args.use_sheets:
        blocked.append("--apply requires --use-sheets")
    if args.limit < 1 or args.limit > 5:
        blocked.append("--limit must be 1..5")
    if blocked:
        print(json.dumps({"status": "BLOCKED", "blocked_reasons": blocked}, ensure_ascii=False, indent=2))
        return 1

    client = load_sheets() if args.use_sheets else None
    source_videos, transcripts = load_rows(client) if client else ([], [])
    selected, skipped = eligible_videos(source_videos, transcripts, account_id=args.account_id, limit=args.limit)
    transcript_rows = []
    source_updates = []
    summaries = []
    for video in selected:
        if args.dry_run or not args.apply:
            summaries.append({
                "source_video_id": video.get("source_video_id", ""),
                "status": "PLAN_ONLY",
                "provider_plan": "youtube_captions_then_local_whisper",
                "preview": "",
            })
            continue
        row, summary = transcribe_one(video, model_size=args.model_size, allow_local_whisper=args.allow_local_whisper)
        transcript_rows.append(row)
        source_updates.append({
            **video,
            "transcript_status": row["transcription_status"],
            "analysis_status": "TRANSCRIBED" if row["transcription_status"] == "DONE" else "TRANSCRIPT_UNAVAILABLE",
            "processed_at": now_iso(),
            "skip_reason": row.get("error", ""),
        })
        summaries.append(summary)
    save_result = {"transcripts_saved": 0, "source_videos_updated": 0, "failed": 0}
    if args.apply and client:
        save_result = save_rows(client, transcript_rows, source_updates)
    out = {
        "status": "DONE" if args.apply else "PLAN_ONLY",
        "account_id": args.account_id,
        "selected_count": len(selected),
        "skipped_count": len(skipped),
        "selected_source_video_ids": [v.get("source_video_id", "") for v in selected],
        "transcription_results": summaries,
        "whisper_processing_seconds": round(sum(float(row.get("processing_seconds") or 0) for row in summaries), 3),
        "transcript_text_logged": False,
        "would_save_transcripts": bool(args.apply and args.confirm_transcribe and args.use_sheets),
        "save_result": save_result,
        "skipped_preview": skipped[:20],
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 1 if save_result.get("failed") else 0


if __name__ == "__main__":
    raise SystemExit(main())
