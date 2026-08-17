"""Beauty-specific voice corpus contract and deterministic style fingerprint."""
from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping


ROOT = Path(__file__).resolve().parents[2]
PROFILE_PATH = ROOT / "config" / "beauty_voice_profile.json"


def load_beauty_voice_profile(path: Path = PROFILE_PATH) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def beauty_voice_prompt() -> str:
    profile = load_beauty_voice_profile()
    fingerprint = profile["style_fingerprint"]
    return (
        "Chadult Beauty Voiceで書く。特定人物の文体や文章はコピーしない。"
        "20〜30代の美容好きに、少しお姉さん寄りの女友達が一対一で話す。"
        f"絵文字は{''.join(fingerprint['allowed_emojis'])}から1〜4個。"
        "句点の。はほとんど使わず、短い文と改行でSNSらしいリズムを作る。"
        "〜なんだけど、これ結構大事、個人的には、ほんとに、意外と、"
        "〜な気がする、〜してみてほしい等を文脈に合わせて2つ以上使う。"
        "共感または気づき、個人的な視点、実用情報の順にする。"
        "実在しない体験は作らず、広告・報告書・コンサル口調にしない。"
    )


def _emoji_count(text: str, allowed: Iterable[str]) -> tuple[int, list[str]]:
    allowed_values = list(allowed)
    hits = [emoji for emoji in allowed_values for _ in range(text.count(emoji))]
    return len(hits), hits


def beauty_style_fingerprint_validation(text: str) -> dict[str, Any]:
    value = str(text or "").strip()
    profile = load_beauty_voice_profile()
    fingerprint = profile["style_fingerprint"]
    isolation = profile["account_isolation"]
    nonempty_lines = [line.strip() for line in value.splitlines() if line.strip()]
    paragraphs = [item.strip() for item in re.split(r"\n\s*\n", value) if item.strip()]
    average_line_length = (
        sum(len(line) for line in nonempty_lines) / len(nonempty_lines)
        if nonempty_lines
        else 0.0
    )
    sentence_like_count = max(1, len(re.findall(r"[\n。！!?？]", value)))
    full_stop_ratio = value.count("。") / sentence_like_count
    emoji_count, emoji_hits = _emoji_count(value, fingerprint["allowed_emojis"])
    humanity_hits = [term for term in fingerprint["humanity_markers"] if term in value]
    soft_ending_hits = [term for term in fingerprint["soft_endings"] if term in value]
    formal_hits = [term for term in fingerprint["formal_or_ad_phrases"] if term in value]
    foreign_hits = [term for term in isolation["blocked_foreign_context_terms"] if term in value]
    forbidden_first_person = [term for term in ("僕", "ぼく", "俺", "おれ") if term in value]

    reasons: list[str] = []
    score = 100
    if not fingerprint["emoji_count_min"] <= emoji_count <= fingerprint["emoji_count_max"]:
        reasons.append("beauty_voice_emoji_count_out_of_range")
        score -= 22
    if not fingerprint["paragraph_count_min"] <= len(paragraphs) <= fingerprint["paragraph_count_max"]:
        reasons.append("beauty_voice_paragraph_rhythm_out_of_range")
        score -= 16
    if average_line_length > fingerprint["average_line_length_max"]:
        reasons.append("beauty_voice_lines_too_dense")
        score -= 18
    if full_stop_ratio > fingerprint["full_stop_ratio_max"]:
        reasons.append("beauty_voice_full_stop_ratio_too_high")
        score -= 18
    if value.count("！") + value.count("!") > fingerprint["exclamation_count_max"]:
        reasons.append("beauty_voice_exclamation_overuse")
        score -= 12
    if len(humanity_hits) < fingerprint["minimum_humanity_marker_count"]:
        reasons.append("beauty_voice_humanity_insufficient")
        score -= 22
    if len(soft_ending_hits) < fingerprint["minimum_soft_ending_count"]:
        reasons.append("beauty_voice_soft_cadence_insufficient")
        score -= 18
    if formal_hits:
        reasons.append("beauty_voice_formal_or_ad_tone")
        score -= min(40, len(formal_hits) * 20)
    if forbidden_first_person:
        reasons.append("beauty_voice_first_person_mismatch")
        score -= 50
    if foreign_hits:
        reasons.append("beauty_voice_cross_account_context_detected")
        score -= 50

    score = max(0, min(100, score))
    if score < fingerprint["minimum_style_score"]:
        reasons.append("beauty_style_fingerprint_score_below_threshold")
    reasons = sorted(set(reasons))
    return {
        "status": "VOICE_PERSONA_PASS" if not reasons else "BLOCKED",
        "score": score,
        "minimum_score": fingerprint["minimum_style_score"],
        "style_profile_version": profile["style_profile_version"],
        "reasons": reasons,
        "details": {
            "voice_profile_version": profile["style_profile_version"],
            "first_person": "私",
            "first_person_status": "PASS" if not forbidden_first_person else "BLOCKED",
            "emoji_count": emoji_count,
            "emoji_hits": emoji_hits,
            "paragraph_count": len(paragraphs),
            "average_line_length": round(average_line_length, 2),
            "full_stop_ratio": round(full_stop_ratio, 4),
            "humanity_marker_hits": humanity_hits,
            "soft_cadence_hits": soft_ending_hits,
            "formal_phrase_hits": formal_hits,
            "cross_account_context_hits": foreign_hits,
            "business_polite_ratio": round(full_stop_ratio, 4),
            "formal_consultant_penalty": min(100, len(formal_hits) * 25),
            "conversational_style_score": score,
            "feminine_warmth_score": min(100, 45 + emoji_count * 8 + len(humanity_hits) * 12 + len(soft_ending_hits) * 8),
        },
    }


def build_voice_corpus_summary(rows: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Aggregate style signals from Beauty-only source posts without copying text."""
    profile = load_beauty_voice_profile()
    allowed_ids = set(profile["voice_reference_source_ids"])
    minimum = int(profile["corpus_policy"]["minimum_posts_per_source"])
    maximum = int(profile["corpus_policy"]["maximum_posts_per_source"])
    maximum_sources = int(profile["corpus_policy"]["maximum_source_accounts"])
    by_source: dict[str, list[str]] = defaultdict(list)
    for row in rows:
        source_id = str(row.get("source_id") or row.get("source_account_id") or "").strip()
        target = str(row.get("target_account_id") or row.get("account_id") or "").strip()
        text = str(row.get("original_post_text") or row.get("post_text") or row.get("text") or "").strip()
        if source_id not in allowed_ids or target != "beauty_account" or not text:
            continue
        if source_id not in by_source and len(by_source) >= maximum_sources:
            continue
        if len(by_source[source_id]) < maximum:
            by_source[source_id].append(text)
    emoji_counts: Counter[str] = Counter()
    total_lines = 0
    total_characters = 0
    for posts in by_source.values():
        for value in posts:
            for emoji in profile["style_fingerprint"]["allowed_emojis"]:
                emoji_counts[emoji] += value.count(emoji)
            lines = [line for line in value.splitlines() if line.strip()]
            total_lines += len(lines)
            total_characters += sum(len(line.strip()) for line in lines)
    post_count = sum(len(posts) for posts in by_source.values())
    eligible_source_count = sum(1 for posts in by_source.values() if len(posts) >= minimum)
    return {
        "status": "READY" if eligible_source_count >= profile["corpus_policy"]["minimum_source_accounts"] else "INSUFFICIENT_CORPUS",
        "style_profile_version": profile["style_profile_version"],
        "source_account_count": len(by_source),
        "eligible_source_account_count": eligible_source_count,
        "post_count": post_count,
        "posts_per_source": {key: len(value) for key, value in sorted(by_source.items())},
        "emoji_frequency": dict(emoji_counts),
        "average_line_length": round(total_characters / total_lines, 2) if total_lines else 0.0,
        "raw_post_text_included": False,
    }
