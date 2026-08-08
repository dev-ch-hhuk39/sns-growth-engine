"""Current reference-source adapter with strict video/transcript identity joins.

`source_posts` is the canonical collection table. Video semantics are joined at
read time from `source_videos` and `video_transcripts`; transcript bodies are not
copied back into source_posts. Every video match is fail-closed on native video
identity so channel/profile URLs can never fan out to many videos.
"""
from __future__ import annotations

import json
import math
import re
from typing import Any
from urllib.parse import parse_qs, urlsplit

VIDEO_PLATFORMS = {"youtube", "youtube_shorts", "tiktok"}
TEXT_PLATFORMS = {"threads", "x", "twitter"}
DONE_TRANSCRIPT_STATUSES = {
    "DONE",
    "FETCHED",
    "LOCAL_WHISPER_DONE",
    "YOUTUBE_CAPTIONS_DONE",
}
TERMINAL_TRANSCRIPT_STATUSES = {
    "NO_RELIABLE_SPEECH",
    "MEDIA_ACQUISITION_BLOCKED",
}
YOUTUBE_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")
TIKTOK_ID = re.compile(r"^[0-9]{10,30}$")

_NIGHT_KEYWORDS = (
    "キャバ", "夜職", "体験", "入店", "時給", "売上", "黒服", "客層", "お客",
    "店舗", "新店舗", "歌舞伎", "六本木", "担当", "案内", "スカウト", "指名",
)
_LIVER_KEYWORDS = (
    "配信", "ライバー", "live", "ライブ", "tiktok", "ギフト", "ギフター", "初見",
    "同接", "コメント", "フォロー", "視聴", "投げ銭", "ダイヤ", "リスナー", "ファン",
    "イベント", "配信者", "配信枠",
)


def _clean(value: Any) -> str:
    return str(value or "").strip()


def normalize_platform(row_or_value: dict[str, Any] | str) -> str:
    if isinstance(row_or_value, dict):
        value = _clean(row_or_value.get("source_platform") or row_or_value.get("platform")).lower()
    else:
        value = _clean(row_or_value).lower()
    if value in {"youtube", "youtube_shorts", "yt"}:
        return "youtube"
    if value in {"tiktok", "tt"}:
        return "tiktok"
    if value in {"twitter", "x"}:
        return "x"
    return value


def _valid_native_id(platform: str, value: Any) -> str:
    candidate = _clean(value)
    if platform == "youtube" and YOUTUBE_ID.fullmatch(candidate):
        return candidate
    if platform == "tiktok" and TIKTOK_ID.fullmatch(candidate):
        return candidate
    return ""


def _video_id_from_url(platform: str, value: Any) -> str:
    raw = _clean(value)
    if not raw:
        return ""
    try:
        parts = urlsplit(raw)
    except ValueError:
        return ""
    host = parts.netloc.lower().split(":", 1)[0]
    path_parts = [part for part in parts.path.split("/") if part]
    if platform == "youtube":
        if host in {"youtu.be", "www.youtu.be"} and path_parts:
            return _valid_native_id("youtube", path_parts[0])
        if host.endswith("youtube.com"):
            query_id = (parse_qs(parts.query).get("v") or [""])[0]
            valid = _valid_native_id("youtube", query_id)
            if valid:
                return valid
            if len(path_parts) >= 2 and path_parts[0].lower() in {"shorts", "embed", "live", "v"}:
                return _valid_native_id("youtube", path_parts[1])
        return ""
    if platform == "tiktok":
        match = re.search(r"/video/([0-9]{10,30})(?:/|$)", parts.path)
        return _valid_native_id("tiktok", match.group(1) if match else "")
    return ""


def native_video_id(row: dict[str, Any]) -> str:
    """Return only an individual platform-native video id; never a profile id."""
    platform = normalize_platform(row)
    for key in ("external_post_id", "video_id"):
        valid = _valid_native_id(platform, row.get(key))
        if valid:
            return valid
    for key in (
        "canonical_post_url",
        "canonical_video_url",
        "original_video_url",
        "post_url",
        "source_url",
    ):
        valid = _video_id_from_url(platform, row.get(key))
        if valid:
            return valid
    return ""


def resolve_source_video(
    source_post: dict[str, Any],
    source_videos: list[dict[str, Any]],
) -> dict[str, Any]:
    """Match by platform + native video id + compatible source/account identity."""
    platform = normalize_platform(source_post)
    video_id = native_video_id(source_post)
    if platform not in {"youtube", "tiktok"} or not video_id:
        return {"status": "UNMATCHED", "reason": "native_video_id_missing", "video_id": video_id, "matches": []}
    source_id = _clean(source_post.get("source_id"))
    account_id = _clean(source_post.get("target_account_id") or source_post.get("account_id"))
    matches: list[dict[str, Any]] = []
    for video in source_videos:
        if normalize_platform(video) != platform:
            continue
        if native_video_id(video) != video_id:
            continue
        video_source_id = _clean(video.get("source_id"))
        if source_id and video_source_id and source_id != video_source_id:
            continue
        video_account_id = _clean(video.get("account_id") or video.get("target_account_id"))
        if account_id and video_account_id and account_id != video_account_id:
            continue
        matches.append(dict(video))
    if len(matches) == 1:
        return {"status": "MATCHED", "reason": "", "video_id": video_id, "match": matches[0], "matches": matches}
    if not matches:
        return {"status": "UNMATCHED", "reason": "exact_native_video_not_found", "video_id": video_id, "matches": []}
    return {
        "status": "AMBIGUOUS",
        "reason": "duplicate_exact_native_video_identity",
        "video_id": video_id,
        "matches": matches,
    }


def resolve_transcript(
    source_video: dict[str, Any],
    transcripts: list[dict[str, Any]],
) -> dict[str, Any]:
    source_video_id = _clean(source_video.get("source_video_id"))
    account_id = _clean(source_video.get("account_id"))
    candidates: list[dict[str, Any]] = []
    terminal_candidates: list[dict[str, Any]] = []
    for transcript in transcripts:
        if _clean(transcript.get("source_video_id")) != source_video_id:
            continue
        transcript_account = _clean(transcript.get("account_id"))
        if account_id and transcript_account and transcript_account != account_id:
            continue
        status = _clean(transcript.get("transcription_status")).upper()
        if status in TERMINAL_TRANSCRIPT_STATUSES:
            terminal_candidates.append(dict(transcript))
            continue
        if status not in DONE_TRANSCRIPT_STATUSES:
            continue
        if not _clean(transcript.get("transcript_text")):
            continue
        candidates.append(dict(transcript))
    if len(candidates) == 1:
        return {"status": "READY", "match": candidates[0], "matches": candidates}
    if not candidates and terminal_candidates:
        terminal_candidates.sort(
            key=lambda row: (
                _clean(row.get("updated_at")),
                _clean(row.get("transcript_id")),
            ),
            reverse=True,
        )
        latest = terminal_candidates[0]
        return {
            "status": "TERMINAL",
            "reason": "terminal_transcript_state",
            "terminal_status": _clean(latest.get("transcription_status")).upper(),
            "match": latest,
            "matches": terminal_candidates,
        }
    if not candidates:
        return {"status": "MISSING", "reason": "completed_transcript_not_found", "matches": []}
    hashes = {
        _clean(row.get("transcript_hash")) or _clean(row.get("transcript_text"))
        for row in candidates
    }
    if len(hashes) == 1:
        candidates.sort(
            key=lambda row: (
                _clean(row.get("updated_at")),
                _clean(row.get("transcript_id")),
            ),
            reverse=True,
        )
        return {
            "status": "READY",
            "match": candidates[0],
            "matches": candidates,
            "duplicate_equivalent": True,
        }
    return {
        "status": "AMBIGUOUS",
        "reason": "multiple_distinct_completed_transcripts",
        "matches": candidates,
    }


def enrich_source_post(
    source_post: dict[str, Any],
    source_videos: list[dict[str, Any]],
    transcripts: list[dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Create a legacy-compatible generation row without mutating any source row."""
    row = dict(source_post)
    platform = normalize_platform(row)
    row["platform"] = platform
    row["source_platform"] = platform
    row["post_id"] = _clean(row.get("source_post_id") or row.get("post_id"))
    row["post_url"] = _clean(row.get("canonical_post_url") or row.get("post_url"))
    row["account_id"] = _clean(row.get("target_account_id") or row.get("account_id"))
    original_text = _clean(row.get("original_post_text") or row.get("post_text") or row.get("text"))
    if original_text:
        row["original_post_text"] = original_text
        row["post_text"] = original_text
        row["text"] = original_text

    if platform not in {"youtube", "tiktok"}:
        return row, {"status": "TEXT_READY" if original_text else "TEXT_MISSING"}

    video_result = resolve_source_video(row, source_videos)
    if video_result["status"] != "MATCHED":
        return row, {
            "status": f"VIDEO_{video_result['status']}",
            "reason": video_result.get("reason", ""),
            "video_id": video_result.get("video_id", ""),
            "match_count": len(video_result.get("matches", [])),
        }
    video = dict(video_result["match"])
    row["source_video_id"] = _clean(video.get("source_video_id"))
    row["video_id"] = video_result["video_id"]
    row["title"] = _clean(video.get("title") or row.get("title"))
    row["description"] = _clean(video.get("description_preview") or row.get("description"))
    transcript_result = resolve_transcript(video, transcripts)
    if transcript_result["status"] != "READY":
        return row, {
            "status": f"TRANSCRIPT_{transcript_result['status']}",
            "reason": transcript_result.get("reason", ""),
            "video_id": video_result["video_id"],
            "source_video_id": row["source_video_id"],
            "terminal_status": transcript_result.get("terminal_status", ""),
        }
    transcript = dict(transcript_result["match"])
    transcript_text = _clean(transcript.get("transcript_text"))
    row["transcript_text"] = transcript_text
    # build_generation_rows uses post_text for the similarity guard; for video
    # references the transcript is the semantic primary source.
    row["post_text"] = transcript_text
    row["transcript_id"] = _clean(transcript.get("transcript_id"))
    row["transcription_provider"] = _clean(transcript.get("transcription_provider"))
    return row, {
        "status": "VIDEO_TRANSCRIPT_READY",
        "video_id": video_result["video_id"],
        "source_video_id": row["source_video_id"],
        "transcript_id": row["transcript_id"],
    }


def _engagement(row: dict[str, Any]) -> dict[str, float]:
    raw = row.get("engagement_json")
    payload: dict[str, Any] = {}
    if isinstance(raw, dict):
        payload = raw
    elif _clean(raw):
        try:
            decoded = json.loads(_clean(raw))
            if isinstance(decoded, dict):
                payload = decoded
        except (TypeError, ValueError, json.JSONDecodeError):
            payload = {}
    def num(*keys: str) -> float:
        for key in keys:
            value = payload.get(key, row.get(key))
            try:
                return max(0.0, float(value or 0))
            except (TypeError, ValueError):
                continue
        return 0.0
    return {
        "views": num("views", "view_count", "impressions"),
        "likes": num("likes", "like_count"),
        "comments": num("comments", "comment_count", "replies"),
        "shares": num("shares", "share_count", "reposts"),
    }


def _relevance(account_id: str, text: str) -> int:
    normalized = text.lower()
    keywords = _NIGHT_KEYWORDS if account_id == "night_scout" else _LIVER_KEYWORDS
    return sum(1 for keyword in keywords if keyword.lower() in normalized)


def _score(account_id: str, row: dict[str, Any]) -> float:
    source_text = _clean(row.get("transcript_text") or row.get("post_text") or row.get("original_post_text"))
    engagement = _engagement(row)
    relevance = _relevance(account_id, source_text)
    return (
        relevance * 1_000_000.0
        + math.log1p(engagement["views"]) * 1000.0
        + math.log1p(engagement["likes"]) * 100.0
        + math.log1p(engagement["comments"]) * 10.0
        + math.log1p(engagement["shares"])
    )


def build_current_reference_generation_inputs(
    *,
    account_id: str,
    source_posts: list[dict[str, Any]],
    source_videos: list[dict[str, Any]],
    transcripts: list[dict[str, Any]],
) -> dict[str, Any]:
    """Adapt canonical current collection rows into source-grounded generation inputs."""
    posts: list[dict[str, Any]] = []
    scores: list[dict[str, Any]] = []
    counts = {
        "source_posts_seen": 0,
        "text_ready": 0,
        "video_transcript_ready": 0,
        "video_transcript_missing": 0,
        "video_transcript_terminal": 0,
        "video_unmatched": 0,
        "video_ambiguous": 0,
        "text_missing": 0,
        "internal_or_self_generated": 0,
    }
    details: list[dict[str, Any]] = []
    for source in source_posts:
        target = _clean(source.get("target_account_id") or source.get("account_id"))
        if target != account_id:
            continue
        counts["source_posts_seen"] += 1
        source_account = _clean(source.get("source_account_id")).lower()
        platform = normalize_platform(source)
        if platform in {"system_generated", "system_generated_owned"} or source_account == "system_generated":
            counts["internal_or_self_generated"] += 1
            continue
        row, state = enrich_source_post(source, source_videos, transcripts)
        status = _clean(state.get("status"))
        if status == "TEXT_READY":
            counts["text_ready"] += 1
        elif status == "VIDEO_TRANSCRIPT_READY":
            counts["video_transcript_ready"] += 1
        elif status in {"TRANSCRIPT_MISSING", "TRANSCRIPT_AMBIGUOUS"}:
            counts["video_transcript_missing"] += 1
        elif status == "TRANSCRIPT_TERMINAL":
            counts["video_transcript_terminal"] += 1
        elif status == "VIDEO_UNMATCHED":
            counts["video_unmatched"] += 1
        elif status == "VIDEO_AMBIGUOUS":
            counts["video_ambiguous"] += 1
        elif status == "TEXT_MISSING":
            counts["text_missing"] += 1
        if status not in {"TEXT_READY", "VIDEO_TRANSCRIPT_READY"}:
            if platform in {"youtube", "tiktok"}:
                details.append({
                    "source_post_id": _clean(source.get("source_post_id")),
                    "platform": platform,
                    "video_id": state.get("video_id", ""),
                    "status": status,
                    "reason": state.get("reason", ""),
                    "terminal_status": state.get("terminal_status", ""),
                    "match_count": state.get("match_count", 0),
                })
            continue
        ref_id = _clean(row.get("post_id"))
        if not ref_id:
            continue
        posts.append(row)
        scores.append({
            "account_id": account_id,
            "reference_post_id": ref_id,
            "total_score": _score(account_id, row),
            "reason": "current_source_posts deterministic relevance+engagement ranking",
            "recommended_use": "REFERENCE_ONLY",
        })
    scores.sort(key=lambda item: (float(item["total_score"]), _clean(item["reference_post_id"])), reverse=True)
    return {
        "posts": posts,
        "scores": scores,
        "diagnostics": {
            **counts,
            "generation_ready": len(posts),
            "ambiguous_match_count": counts["video_ambiguous"],
            "unresolved_video_sample": details[:10],
        },
    }
