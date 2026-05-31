"""
transcript_parser.py - 文字起こし結果の解析とクリップ候補抽出

設計:
  - Gemini 等 LLM を使わず、ルールベースで候補セグメントを抽出する（コスト0）
  - LLM による深い分析は将来の Phase で追加する
  - テスト可能・副作用なし（pure functions）
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _short_uuid() -> str:
    return str(uuid.uuid4())[:8]


# 動画全体を1クリップとして扱う最大長（秒）
_MAX_CLIP_DURATION = 300.0
# 短すぎるクリップは除外する最小長（秒）
_MIN_CLIP_DURATION = 15.0


def parse_segments(segments_json_or_list: Any) -> list[dict]:
    """segments_json（JSON文字列またはlist）を list[dict] に変換する。"""
    import json
    if isinstance(segments_json_or_list, list):
        return segments_json_or_list
    if isinstance(segments_json_or_list, str) and segments_json_or_list.strip():
        try:
            return json.loads(segments_json_or_list)
        except Exception:
            return []
    return []


def extract_clip_window(
    segments: list[dict],
    *,
    max_duration: float = _MAX_CLIP_DURATION,
    min_duration: float = _MIN_CLIP_DURATION,
) -> tuple[float, float]:
    """セグメントリストから最適なクリップ区間（start_time, end_time）を返す。

    現実装: 動画全体を1つのクリップ候補として返す（将来は分割ロジックを追加）。
    duration が _MAX_CLIP_DURATION を超える場合は先頭からカット。
    """
    if not segments:
        return (0.0, 0.0)

    starts = [float(s.get("start", 0.0)) for s in segments if "start" in s]
    ends = [float(s.get("end", 0.0)) for s in segments if "end" in s]

    if not starts or not ends:
        return (0.0, 0.0)

    start = min(starts)
    end = max(ends)
    duration = end - start

    if duration < min_duration:
        return (0.0, 0.0)

    if duration > max_duration:
        end = start + max_duration

    return (round(start, 2), round(end, 2))


def extract_hook_sentence(transcript_text: str) -> str:
    """文字起こしテキストから冒頭の「フック」文を抽出する。

    現実装: 最初の句読点（。！？）または最初の30文字を返す。
    """
    if not transcript_text:
        return ""
    for sep in ("。", "！", "？", "!", "?", ".", "\n"):
        idx = transcript_text.find(sep)
        if 0 < idx <= 80:
            return transcript_text[: idx + 1].strip()
    return transcript_text[:40].strip()


def build_clip_candidate(
    transcript: dict[str, Any],
    *,
    account_id: str,
    clip_title: str = "",
) -> dict[str, Any] | None:
    """transcript dict から video_clip_candidates 行を生成する。

    セグメントがなく duration_seconds も 0 の場合は None を返す。
    """
    segments = parse_segments(transcript.get("segments_json", []))
    duration_seconds = float(transcript.get("duration_seconds", 0.0) or 0.0)
    text = str(transcript.get("transcript_text", ""))

    if segments:
        start, end = extract_clip_window(segments)
    else:
        start = 0.0
        end = min(duration_seconds, _MAX_CLIP_DURATION)

    clip_duration = end - start
    if clip_duration < _MIN_CLIP_DURATION and duration_seconds >= _MIN_CLIP_DURATION:
        start = 0.0
        end = min(duration_seconds, _MAX_CLIP_DURATION)
        clip_duration = end - start

    if clip_duration <= 0:
        return None

    hook = extract_hook_sentence(text)
    excerpt = text[:200].strip() if text else ""

    return {
        "clip_id": f"clip-{_short_uuid()}",
        "account_id": account_id,
        "reference_post_id": str(transcript.get("reference_post_id", "")),
        "transcript_id": str(transcript.get("transcript_id", "")),
        "source_platform": str(transcript.get("source_platform", "")),
        "source_video_url": str(transcript.get("video_url", "")),
        "start_time": round(start, 2),
        "end_time": round(end, 2),
        "duration_seconds": round(clip_duration, 2),
        "clip_title": clip_title or hook[:60],
        "hook": hook,
        "why_it_works": "",
        "target_persona": "",
        "x_post_angle": "",
        "threads_post_angle": "",
        "transcript_excerpt": excerpt,
        "clip_status": "candidate",
        "media_asset_id": "",
        "storage_url": "",
        "reuse_status": "unused",
        "media_reuse_risk": "low",
        "imitation_risk": "low",
        "rights_status": "unknown",
        "permission_status": "unknown",
        "created_at": _now(),
        "notes": "",
    }


def build_clip_candidates_from_transcripts(
    transcripts: list[dict[str, Any]],
    *,
    account_id: str,
) -> list[dict[str, Any]]:
    """文字起こし結果リストからクリップ候補リストを生成する。"""
    candidates = []
    for t in transcripts:
        if str(t.get("transcription_status", "")).lower() != "done":
            continue
        candidate = build_clip_candidate(t, account_id=account_id)
        if candidate:
            candidates.append(candidate)
    return candidates
