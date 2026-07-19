"""Choose bounded clip ranges from semantic transcript signals."""
from __future__ import annotations

import re
from typing import Any

HOOK_MARKERS = (
    "なぜ", "どうして", "実は", "知らない", "大事", "ポイント", "理由",
    "まず", "コツ", "注意", "失敗", "違い", "変わる", "伸び", "初見",
    "店選び", "移籍", "ノルマ", "客層", "続け", "コメント", "リスナー",
)
ACTION_MARKERS = ("してみ", "確認", "比べ", "伝え", "決め", "書き", "変え", "選ぶ")


def segment_signal_score(segment: dict[str, Any]) -> float:
    text = str(segment.get("text", "")).strip()
    if not text:
        return 0.0
    score = min(len(text) / 40.0, 1.0)
    score += sum(0.45 for marker in HOOK_MARKERS if marker in text)
    score += sum(0.25 for marker in ACTION_MARKERS if marker in text)
    if "?" in text or "？" in text:
        score += 0.55
    if re.search(r"[。！？!?]$", text):
        score += 0.15
    return round(score, 4)


def _duration(segment: dict[str, Any]) -> float:
    return max(0.0, float(segment.get("end", 0)) - float(segment.get("start", 0)))


def _overlap_seconds(left: dict[str, Any], right: dict[str, Any]) -> float:
    return max(0.0, min(float(left["end"]), float(right["end"])) - max(float(left["start"]), float(right["start"])))


def _window_for_anchor(
    segments: list[dict[str, Any]],
    anchor_index: int,
    *,
    min_seconds: float,
    max_seconds: float,
    video_duration: float,
) -> dict[str, Any]:
    start_index = anchor_index
    # Include one short setup utterance when it stays within the bound.
    if anchor_index > 0 and _duration(segments[anchor_index - 1]) <= 6:
        start_index -= 1
    start = max(0.0, float(segments[start_index]["start"]))
    end_index = anchor_index
    end = float(segments[end_index]["end"])
    while end - start < min_seconds and end_index + 1 < len(segments):
        end_index += 1
        candidate_end = float(segments[end_index]["end"])
        if candidate_end - start > max_seconds:
            break
        end = candidate_end
    # Add one explanatory sentence after the hook when room permits.
    while end_index + 1 < len(segments):
        candidate = segments[end_index + 1]
        candidate_end = float(candidate["end"])
        if candidate_end - start > max_seconds:
            break
        end_index += 1
        end = candidate_end
        if re.search(r"[。！？!?]$", str(candidate.get("text", "")).strip()) and end - start >= min_seconds:
            break
    if end - start < min_seconds:
        end = min(video_duration or start + min_seconds, start + min_seconds)
    end = min(end, video_duration) if video_duration else end
    if end - start > max_seconds:
        end = start + max_seconds
    selected = segments[start_index:end_index + 1]
    excerpt = " ".join(str(item.get("text", "")).strip() for item in selected if str(item.get("text", "")).strip())
    return {
        "start": round(start, 3),
        "end": round(end, 3),
        "excerpt": excerpt,
        "semantic_score": round(sum(segment_signal_score(item) for item in selected), 4),
        "selected_reason": "semantic_hook_and_explanation_window",
        "anchor_index": anchor_index,
    }


def plan_semantic_clips(
    segments: list[dict[str, Any]],
    *,
    video_duration: float,
    max_candidates: int,
    min_seconds: float = 8,
    max_seconds: float = 45,
    overlap_tolerance_seconds: float = 2,
) -> list[dict[str, Any]]:
    cleaned = [
        {"start": float(row.get("start", 0)), "end": float(row.get("end", 0)), "text": str(row.get("text", "")).strip()}
        for row in segments
        if str(row.get("text", "")).strip() and float(row.get("end", 0)) > float(row.get("start", 0))
    ]
    if not cleaned or max_candidates <= 0:
        return []
    if video_duration and video_duration < 25:
        start = max(0.0, cleaned[0]["start"])
        end = min(video_duration, max(cleaned[-1]["end"], min_seconds))
        return [{
            "start": round(start, 3),
            "end": round(end, 3),
            "excerpt": " ".join(row["text"] for row in cleaned),
            "semantic_score": round(sum(segment_signal_score(row) for row in cleaned), 4),
            "selected_reason": "short_video_single_semantic_clip",
            "anchor_index": 0,
        }]

    ranked = sorted(range(len(cleaned)), key=lambda index: (-segment_signal_score(cleaned[index]), index))
    accepted: list[dict[str, Any]] = []
    for anchor_index in ranked:
        candidate = _window_for_anchor(
            cleaned,
            anchor_index,
            min_seconds=min_seconds,
            max_seconds=max_seconds,
            video_duration=video_duration,
        )
        if candidate["end"] - candidate["start"] < min_seconds:
            continue
        if any(_overlap_seconds(candidate, old) > overlap_tolerance_seconds for old in accepted):
            continue
        accepted.append(candidate)
        if len(accepted) >= max_candidates:
            break
    return sorted(accepted, key=lambda row: float(row["start"]))
