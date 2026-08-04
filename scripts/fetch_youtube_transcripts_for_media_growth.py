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


SHEETS_SAFE_CELL_CHARS = 40000
YOUTUBE_CHUNK_SCOPE = "youtube_caption_chunk"


def _complete_transcript_row(row: dict[str, Any]) -> bool:
    return (
        _text(
            row.get("transcription_status")
            or row.get("transcript_status")
        ).upper()
        in {
            "DONE",
            "FETCHED",
            "YOUTUBE_CAPTIONS_DONE",
            "LOCAL_WHISPER_DONE",
        }
        and bool(_text(row.get("segments_json")))
    )


def _chunk_scope(row: dict[str, Any]) -> tuple[int, int] | None:
    raw = _text(row.get("transcription_scope"))
    prefix = f"{YOUTUBE_CHUNK_SCOPE}:"
    if not raw.startswith(prefix):
        return None
    try:
        part_text, total_text = raw[len(prefix):].split("/", 1)
        part = int(part_text)
        total = int(total_text)
    except (ValueError, TypeError):
        return None
    if part < 1 or total < 1 or part > total:
        return None
    return part, total


def complete_source_video_ids(
    transcripts: list[dict[str, Any]],
) -> set[str]:
    legacy_complete: set[str] = set()
    chunk_parts: dict[str, set[int]] = {}
    chunk_totals: dict[str, int] = {}

    for row in transcripts:
        if not _complete_transcript_row(row):
            continue
        source_video_id = _text(row.get("source_video_id"))
        if not source_video_id:
            continue
        scope = _chunk_scope(row)
        if scope is None:
            legacy_complete.add(source_video_id)
            continue
        part, total = scope
        chunk_parts.setdefault(source_video_id, set()).add(part)
        chunk_totals[source_video_id] = max(
            total,
            chunk_totals.get(source_video_id, 0),
        )

    complete = set(legacy_complete)
    for source_video_id, total in chunk_totals.items():
        if chunk_parts.get(source_video_id, set()) == set(
            range(1, total + 1)
        ):
            complete.add(source_video_id)
    return complete


def partition_transcript_segments(
    segments: list[dict[str, Any]],
    *,
    max_cell_chars: int = SHEETS_SAFE_CELL_CHARS,
) -> list[list[dict[str, Any]]]:
    chunks: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []

    def encoded_size(rows: list[dict[str, Any]]) -> tuple[int, int]:
        transcript_text = " ".join(
            _text(row.get("text"))
            for row in rows
        ).strip()
        segments_json = json.dumps(
            rows,
            ensure_ascii=False,
            separators=(",", ":"),
        )
        return len(transcript_text), len(segments_json)

    for source in segments:
        row = {
            "start": round(float(source.get("start", 0) or 0), 3),
            "end": round(float(source.get("end", 0) or 0), 3),
            "text": _text(source.get("text")),
        }
        if not row["text"]:
            continue

        candidate = current + [row]
        text_size, json_size = encoded_size(candidate)

        if (
            current
            and max(text_size, json_size) > max_cell_chars
        ):
            chunks.append(current)
            current = [row]
            text_size, json_size = encoded_size(current)
        else:
            current = candidate

        if max(text_size, json_size) > max_cell_chars:
            raise ValueError(
                "single_transcript_segment_exceeds_safe_cell_limit"
            )

    if current:
        chunks.append(current)

    return chunks


def build_transcript_rows(
    *,
    video: dict[str, Any],
    account_id: str,
    segments: list[dict[str, Any]],
    language: str,
) -> list[dict[str, Any]]:
    source_video_id = _text(video.get("source_video_id"))
    if not source_video_id:
        raise ValueError("source_video_id_missing")

    chunks = partition_transcript_segments(segments)
    if not chunks:
        raise ValueError("youtube_transcript_empty")

    total = len(chunks)
    now = datetime.now(
        timezone.utc
    ).replace(microsecond=0).isoformat()
    rows: list[dict[str, Any]] = []

    for index, chunk in enumerate(chunks, start=1):
        transcript_text = " ".join(
            row["text"]
            for row in chunk
        ).strip()
        segments_json = json.dumps(
            chunk,
            ensure_ascii=False,
            separators=(",", ":"),
        )
        if (
            len(transcript_text) > SHEETS_SAFE_CELL_CHARS
            or len(segments_json) > SHEETS_SAFE_CELL_CHARS
        ):
            raise ValueError(
                "transcript_chunk_exceeds_safe_cell_limit"
            )
        start = float(chunk[0]["start"])
        end = float(chunk[-1]["end"])
        duration = max(0.0, end - start)
        rows.append({
            "transcript_id": (
                f"tr_{source_video_id}_part_{index:03d}"
            ),
            "account_id": account_id,
            "reference_post_id": source_video_id,
            "source_video_id": source_video_id,
            "video_id": _text(video.get("video_id")),
            "source_id": _text(video.get("source_id")),
            "source_platform": "youtube",
            "video_url": _text(
                video.get("canonical_video_url")
            ),
            "transcription_provider": (
                "youtube_transcript_api"
            ),
            "transcription_status": (
                "YOUTUBE_CAPTIONS_DONE"
            ),
            "duration_seconds": round(duration, 3),
            "transcript_text": transcript_text,
            "segments_json": segments_json,
            "language": language or "unknown",
            "processed_minutes": round(duration / 60, 4),
            "transcription_scope": (
                f"{YOUTUBE_CHUNK_SCOPE}:{index}/{total}"
            ),
            "processed_duration_seconds": round(
                duration,
                3,
            ),
            "transcript_hash": hashlib.sha256(
                transcript_text.encode("utf-8")
            ).hexdigest(),
            "chunk_count": len(chunk),
            "error": "",
            "created_at": now,
            "updated_at": now,
        })

    return rows


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
    complete = complete_source_video_ids(
        transcripts
    )
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
            transcript_rows = build_transcript_rows(
                video=video,
                account_id=account_id,
                segments=segments,
                language=language,
            )
            write_statuses = [
                _append_or_update(client, row)
                for row in transcript_rows
            ]
            status = (
                "EXISTING_COMPLETE"
                if all(
                    item == "EXISTING_COMPLETE"
                    for item in write_statuses
                )
                else "APPENDED"
                if any(
                    item == "APPENDED"
                    for item in write_statuses
                )
                else "UPDATED"
            )
            result.update({
                "status": status,
                "segment_count": len(segments),
                "chunk_row_count": len(transcript_rows),
                "transcript_ids": [
                    row["transcript_id"]
                    for row in transcript_rows
                ],
                "write_statuses": write_statuses,
                "language": language or "unknown",
            })
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
