#!/usr/bin/env python3
"""Fetch bounded YouTube captions for approved Media Growth sources."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

from config_loader import get_config  # noqa: E402
from final_production_contracts import APPROVED_RIGHTS, is_active_permission  # noqa: E402
from sheets_client import TAB_DEFINITIONS, SheetsClient  # noqa: E402
from sheets_record_reader import read_records_safely  # noqa: E402


def _text(value: Any) -> str:
    return str(value or "").strip()


def _records(client: SheetsClient, logical: str) -> list[dict[str, Any]]:
    client._ensure_tab(logical, TAB_DEFINITIONS[logical])
    return [dict(row) for row in read_records_safely(client, logical)]


def _active_clip_permission(permissions: list[dict[str, Any]], *, account_id: str, source_id: str) -> dict[str, Any]:
    for row in permissions:
        if _text(row.get("account_id")) != account_id or _text(row.get("source_id")) != source_id:
            continue
        if is_active_permission(row, account_id=account_id, operation="clip"):
            return dict(row)
    return {}


def normalize_segments(fetched: Any) -> list[dict[str, Any]]:
    raw: Iterable[Any] = fetched.to_raw_data() if hasattr(fetched, "to_raw_data") else fetched
    segments: list[dict[str, Any]] = []
    for item in raw:
        body = item if isinstance(item, dict) else {
            "text": getattr(item, "text", ""),
            "start": getattr(item, "start", 0),
            "duration": getattr(item, "duration", 0),
        }
        text = _text(body.get("text"))
        if not text:
            continue
        try:
            start = float(body.get("start", 0) or 0)
            duration = float(body.get("duration", 0) or 0)
        except (TypeError, ValueError):
            continue
        segments.append({"start": round(start, 3), "end": round(start + max(duration, 0.05), 3), "text": text})
    return segments


def fetch_youtube_segments(video_id: str) -> tuple[list[dict[str, Any]], str]:
    from youtube_transcript_api import YouTubeTranscriptApi
    api = YouTubeTranscriptApi()
    try:
        fetched = api.fetch(video_id, languages=["ja", "ja-JP", "en"])
        language = _text(getattr(fetched, "language_code", ""))
    except Exception as first_error:
        legacy = getattr(YouTubeTranscriptApi, "get_transcript", None)
        if legacy is None:
            raise first_error
        fetched = legacy(video_id, languages=["ja", "ja-JP", "en"])
        language = "unknown"
    return normalize_segments(fetched), language


def _append_or_update(client: SheetsClient, row: dict[str, Any]) -> str:
    from gspread.utils import rowcol_to_a1
    logical = "video_transcripts"
    client._ensure_tab(logical, TAB_DEFINITIONS[logical])
    ws = client._ws(logical)
    headers = client._call_with_rate_limit_retry("row_values:video_transcripts:bounded_fetch", lambda: ws.row_values(1))
    existing = client._call_with_rate_limit_retry("get_all_records:video_transcripts:bounded_fetch", lambda: ws.get_all_records())
    transcript_id = _text(row.get("transcript_id"))
    for row_number, old in enumerate(existing, start=2):
        if _text(old.get("transcript_id")) != transcript_id:
            continue
        old_status = _text(old.get("transcription_status") or old.get("transcript_status")).upper()
        if old_status in {"DONE", "FETCHED", "YOUTUBE_CAPTIONS_DONE", "LOCAL_WHISPER_DONE"} and _text(old.get("segments_json")):
            return "EXISTING_COMPLETE"
        merged = {**dict(old), **row}
        target = f"{rowcol_to_a1(row_number, 1)}:{rowcol_to_a1(row_number, len(headers))}"
        client._call_with_rate_limit_retry(
            "batch_update:video_transcripts:bounded_fetch",
            lambda: ws.batch_update([{"range": target, "values": [[str(merged.get(h, "")) for h in headers]]}], value_input_option="USER_ENTERED"),
        )
        return "UPDATED"
    client._call_with_rate_limit_retry(
        "append_row:video_transcripts:bounded_fetch",
        lambda: ws.append_row([str(row.get(h, "")) for h in headers], value_input_option="USER_ENTERED"),
    )
    return "APPENDED"


def build_plan(*, client: SheetsClient, account_id: str, max_videos: int, apply: bool) -> dict[str, Any]:
    source_videos = _records(client, "source_videos")
    transcripts = _records(client, "video_transcripts")
    permissions = _records(client, "media_permissions")
    complete = {
        _text(row.get("source_video_id"))
        for row in transcripts
        if _text(row.get("transcription_status") or row.get("transcript_status")).upper()
        in {"DONE", "FETCHED", "YOUTUBE_CAPTIONS_DONE", "LOCAL_WHISPER_DONE"}
        and _text(row.get("segments_json"))
    }
    candidates: list[tuple[dict[str, Any], dict[str, Any]]] = []
    rejected: list[dict[str, Any]] = []
    for video in source_videos:
        if _text(video.get("account_id")) != account_id or _text(video.get("platform")).lower() != "youtube":
            continue
        source_video_id = _text(video.get("source_video_id"))
        if not source_video_id or source_video_id in complete:
            continue
        source_id = _text(video.get("source_id"))
        blockers: list[str] = []
        if _text(video.get("rights_status")).lower() not in APPROVED_RIGHTS:
            blockers.append("rights_status_not_approved")
        if _text(video.get("permission_status")).lower() != "approved":
            blockers.append("row_permission_not_approved")
        permission = _active_clip_permission(permissions, account_id=account_id, source_id=source_id)
        if not permission:
            blockers.append("active_clip_permission_missing")
        video_id = _text(video.get("video_id"))
        if len(video_id) != 11:
            blockers.append("youtube_video_id_invalid")
        if blockers:
            rejected.append({"source_video_id": source_video_id, "source_id": source_id, "blockers": sorted(set(blockers))})
            continue
        candidates.append((dict(video), permission))
    candidates.sort(key=lambda pair: (_text(pair[0].get("discovered_at")), _text(pair[0].get("source_video_id"))), reverse=True)
    selected = candidates[:max_videos]
    results: list[dict[str, Any]] = []
    for video, permission in selected:
        source_video_id = _text(video.get("source_video_id"))
        video_id = _text(video.get("video_id"))
        result = {
            "source_video_id": source_video_id,
            "source_id": _text(video.get("source_id")),
            "video_id": video_id,
            "permission_id": _text(permission.get("permission_id") or permission.get("media_permission_id")),
            "status": "PLANNED",
            "segment_count": 0,
            "error": "",
        }
        if not apply:
            results.append(result)
            continue
        try:
            segments, language = fetch_youtube_segments(video_id)
            if not segments:
                raise RuntimeError("youtube_transcript_empty")
            transcript_text = " ".join(row["text"] for row in segments).strip()
            transcript_id = f"tr_{source_video_id}"
            now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
            row = {
                "transcript_id": transcript_id,
                "source_video_id": source_video_id,
                "source_id": _text(video.get("source_id")),
                "source_url": _text(video.get("canonical_video_url")),
                "account_id": account_id,
                "platform": "youtube",
                "video_id": video_id,
                "title": _text(video.get("title")),
                "transcript_status": "YOUTUBE_CAPTIONS_DONE",
                "transcription_status": "YOUTUBE_CAPTIONS_DONE",
                "transcript_language": language or "unknown",
                "transcript_text": transcript_text,
                "transcript_text_redacted_preview": transcript_text[:120],
                "transcript_hash": hashlib.sha256(transcript_text.encode("utf-8")).hexdigest(),
                "chunk_count": len(segments),
                "segments_json": json.dumps(segments, ensure_ascii=False, separators=(",", ":")),
                "provider_name": "youtube_transcript_api",
                "provider_version": "1",
                "created_at": now,
                "updated_at": now,
                "rights_status": _text(video.get("rights_status")),
                "permission_status": "approved",
            }
            status = _append_or_update(client, row)
            result.update({"status": status, "segment_count": len(segments), "transcript_id": transcript_id, "language": language or "unknown"})
        except Exception as exc:
            result.update({"status": "FAILED", "error": f"{type(exc).__name__}:{str(exc)[:300]}"})
        results.append(result)
    return {
        "schema_version": "bounded_youtube_transcript_fetch_v1",
        "status": "COMPLETE",
        "account_id": account_id,
        "candidate_count": len(candidates),
        "selected_count": len(selected),
        "successful_count": sum(row["status"] in {"APPENDED", "UPDATED", "EXISTING_COMPLETE"} for row in results),
        "failed_count": sum(row["status"] == "FAILED" for row in results),
        "results": results,
        "rejected": rejected,
        "safety": {"media_download": False, "media_cut": False, "media_upload": False, "queue_write": False, "ready_transition": False, "sns_post": False},
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="fetch bounded approved YouTube transcripts")
    parser.add_argument("--account-id", required=True, choices=["liver_manager", "night_scout"])
    parser.add_argument("--max-videos", type=int, default=3)
    parser.add_argument("--use-sheets", action="store_true")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm-transcription", action="store_true")
    args = parser.parse_args()
    blocked: list[str] = []
    if not args.use_sheets:
        blocked.append("--use-sheets required")
    if args.apply and not args.confirm_transcription:
        blocked.append("--apply requires --confirm-transcription")
    if blocked:
        print(json.dumps({"status": "BLOCKED", "blocked_reasons": blocked}, ensure_ascii=False, indent=2))
        return 1
    cfg = get_config()
    client = SheetsClient(cfg["sheet_id"], cfg["sa_dict"], dry_run=not args.apply)
    plan = build_plan(client=client, account_id=args.account_id, max_videos=max(1, min(args.max_videos, 5)), apply=args.apply)
    print(json.dumps(plan, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
