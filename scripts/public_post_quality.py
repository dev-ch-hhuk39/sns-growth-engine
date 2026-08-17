#!/usr/bin/env python3
"""Public post generation and final validation gates.

Only ``public_post_text`` may ever be handed to a publisher. Internal
analysis, reference metadata, and scoring notes must stay out of public text.
"""
from __future__ import annotations

import difflib
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from accounts.beauty_policy import beauty_compliance_validation  # noqa: E402

RULES_FILE = ROOT / "config/post_generation_rules.json"
VOICE_PROFILES_FILE = ROOT / "config/account_voice_profiles.json"

INTERNAL_LEAK_TERMS = [
    "今回の切り口",
    "threads /",
    "night_work_scout",
    "night_scout",
    "liver_manager",
    "target_account_id",
    "source",
    "reference",
    "参照元",
    "source_url",
    "source_id",
    "queue_id",
    "result_id",
    "category",
    "usage_scope",
    "trend_signal",
    "clip_candidate",
    "投稿案",
    "生成",
    "分解して使う",
    "そのまま真似るのではなく",
    "構成・フック",
    "投稿アイデア",
    "LINE/DMへの導線は最後",
    "導線は最後",
    "AI",
    "内部",
    "metadata",
    "transcript",
    "youtube_video_id_missing",
    "PLAN_ONLY",
    "AUTO_READY",
    "WAITING_REVIEW",
    "dry-run",
    "apply",
    "score",
    "safety_score",
    "risk_score",
]

SOURCE_METADATA_PATTERNS = [
    r"\bthreads\s*/",
    r"\bx\.com/",
    r"\byoutube\.com/",
    r"\btiktok\.com/",
    r"\bhttps?://",
    r"\bsource[_-]?\w*",
    r"\bqueue[_-]?\w*",
    r"\bresult[_-]?\w*",
]

AGGRESSIVE_OR_RISKY_TERMS = [
    "絶対稼げる",
    "必ず稼げる",
    "100%稼げる",
    "確実に稼げる",
    "誰でも月収",
    "楽して稼げる",
    "保証します",
    "今すぐ応募",
    "即日で稼げる",
    "ノーリスク",
]

ACCOUNT_TERMS = {
    "night_scout": ("夜職", "キャバ", "店", "働く", "時給", "ノルマ", "担当", "相談", "出勤", "移籍"),
    "liver_manager": ("配信", "ライバー", "TikTok LIVE", "LIVE", "リスナー", "初見", "コメント", "事務所", "ギフト"),
    "beauty_account": ("コスメ", "スキンケア", "肌", "メイク", "ファンデ", "髪", "ヘアケア", "美容家電", "サロン"),
}


def load_post_generation_rules(path: Path = RULES_FILE) -> dict[str, Any]:
    if not path.exists():
        return {"quality_thresholds": {}, "accounts": {}, "account_execution": {}}
    return json.loads(path.read_text(encoding="utf-8"))


def load_account_voice_profiles(path: Path = VOICE_PROFILES_FILE) -> dict[str, Any]:
    """Load the single canonical source for public account voice."""
    if not path.exists():
        return {"schema_version": "missing", "semantic_voice_score_min": 85, "accounts": {}}
    value = json.loads(path.read_text(encoding="utf-8"))
    return value if isinstance(value, dict) else {"accounts": {}}


def canonical_voice_profile(account_id: str) -> dict[str, Any]:
    profiles = load_account_voice_profiles().get("accounts", {})
    profile = profiles.get(account_id, {}) if isinstance(profiles, dict) else {}
    return dict(profile) if isinstance(profile, dict) else {}


def canonical_voice_prompt(account_id: str) -> str:
    """Return the exact generation/review contract consumed by runtime prompts."""
    return str(canonical_voice_profile(account_id).get("prompt_contract", "")).strip()


def extract_public_post_text(value: Any) -> str:
    """Return public text only, even when passed structured generation output."""
    if isinstance(value, dict):
        return str(value.get("public_post_text", "")).strip()
    raw = str(value or "").strip()
    if raw.startswith("{") and "public_post_text" in raw:
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                return str(parsed.get("public_post_text", "")).strip()
        except json.JSONDecodeError:
            return ""
    return raw


def build_generation_output(
    *,
    internal_analysis: str,
    public_post_text: str,
    safety_notes: str = "",
    blocked_reasons: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "internal_analysis": internal_analysis,
        "public_post_text": public_post_text,
        "safety_notes": safety_notes,
        "blocked_reasons": list(blocked_reasons or []),
    }


def _contains_terms(text: str, terms: list[str]) -> list[str]:
    low = text.lower()
    return [term for term in terms if term and term.lower() in low]


def _risk_score(text: str) -> int:
    score = 0
    if _contains_terms(text, AGGRESSIVE_OR_RISKY_TERMS):
        score += 30
    if any(k in text for k in ("絶対", "必ず", "保証", "誰でも", "簡単に稼げる")):
        score += 15
    if any(k in text for k in ("晒す", "叩く", "詐欺", "未成年", "薬")):
        score += 30
    return min(100, score)


def _cta_pressure_score(text: str) -> int:
    score = 0
    if any(k in text for k in ("今すぐ", "絶対", "必ず", "急いで", "限定")):
        score += 25
    if text.count("DM") + text.count("LINE") >= 2:
        score += 20
    if any(k in text for k in ("応募", "登録", "申し込み")):
        score += 15
    return min(100, score)


def _naturalness_score(
    text: str,
    account_id: str = "",
) -> int:
    if not text.strip():
        return 0
    score = 86
    if (
        "。" not in text
        and account_id != "liver_manager"
    ):
        score -= 15
    if len(text) < 80 or len(text) > 520:
        score -= 18
    if len(text.splitlines()) > 16:
        score -= 10
    if re.search(r"[A-Za-z_]{12,}", text):
        score -= 25
    if _contains_terms(text, INTERNAL_LEAK_TERMS):
        score -= 50
    return max(0, min(100, score))


def _reader_value_score(text: str, account_id: str) -> int:
    value_terms = ("理由", "大事", "まず", "見る", "整理", "変わる", "選ぶ", "続かない", "入りやすい", "具体")
    score = 72 + min(18, sum(1 for term in value_terms if term in text) * 4)
    if len(text) < 80:
        score -= 20
    if account_id == "night_scout" and any(k in text for k in ("店", "時給", "ノルマ", "担当", "出勤", "相談")):
        score += 8
    if account_id == "liver_manager" and any(k in text for k in ("初見", "コメント", "配信", "リスナー", "空気")):
        score += 8
    if account_id == "beauty_account" and any(k in text for k in ACCOUNT_TERMS["beauty_account"]):
        score += 8
    return max(0, min(100, score))


def _voice_sentence_units(text: str) -> list[str]:
    units = []
    for item in re.split(r"(?<=[。！？!?])|\n+", str(text or "")):
        value = re.sub(r"^[・●■□\-\s]+", "", item.strip())
        if value:
            units.append(value)
    return units


def _business_polite_ending(sentence: str) -> bool:
    value = re.sub(r"[。！？!?\s]+$", "", str(sentence or "").strip())
    return bool(
        re.search(
            r"(?:です|ます|ました|ません|ましょう|ください|できます|なります|"
            r"おります|いたします|思います|見ています|示します|判断します|確認します)$",
            value,
        )
    )


def voice_persona_validation(text: str, account_id: str) -> dict[str, Any]:
    """Measure account voice separately from subject-matter/account fit."""
    profile = canonical_voice_profile(account_id)
    if not profile:
        return {
            "status": "BLOCKED",
            "score": 0,
            "reasons": ["voice_profile_missing"],
            "details": {},
        }

    value = str(text or "").strip()
    sentences = _voice_sentence_units(value)
    sentence_count = max(1, len(sentences))
    polite_sentences = [sentence for sentence in sentences if _business_polite_ending(sentence)]
    polite_ratio = len(polite_sentences) / sentence_count
    max_ratio = float(profile.get("business_polite_ratio_max", 0.4))
    first_person = str(profile.get("first_person", ""))
    first_person_count = value.count(first_person) if first_person else 0
    forbidden_first_person = [str(item) for item in profile.get("forbidden_first_person", []) if str(item)]
    first_person_mismatches = [item for item in forbidden_first_person if item in value]
    formal_phrases = [str(item) for item in profile.get("formal_consultant_phrases", []) if str(item)]
    formal_hits = [item for item in formal_phrases if item in value]
    preferred = [str(item) for item in profile.get("preferred_cadence", []) if str(item)]
    preferred_hits = [item for item in preferred if item in value]
    reasons: list[str] = []
    score = 100

    if first_person_mismatches:
        reasons.append("voice_first_person_mismatch")
        score -= 50
    if first_person_count > 3:
        reasons.append("voice_first_person_overuse")
        score -= min(20, (first_person_count - 3) * 5)
    if polite_ratio > max_ratio:
        reasons.append("voice_business_polite_ratio_exceeded")
        score -= 35 + min(20, int((polite_ratio - max_ratio) * 50))
    if formal_hits:
        reasons.append("voice_formal_consultant_phrase_present")
        score -= min(36, len(formal_hits) * 12)
    if value.count("ください") >= 2:
        reasons.append("voice_repeated_business_command")
        score -= 20

    details: dict[str, Any] = {
        "voice_profile_version": load_account_voice_profiles().get("schema_version", ""),
        "first_person": first_person,
        "first_person_count": first_person_count,
        "first_person_mismatches": first_person_mismatches,
        "first_person_status": "PASS" if not first_person_mismatches else "BLOCKED",
        "sentence_count": len(sentences),
        "business_polite_sentence_count": len(polite_sentences),
        "business_polite_ratio": round(polite_ratio, 4),
        "business_polite_ratio_max": max_ratio,
        "formal_consultant_phrase_hits": formal_hits,
        "preferred_cadence_hits": preferred_hits,
    }

    if account_id == "night_scout":
        field_markers = [str(item) for item in profile.get("field_perspective_markers", []) if str(item)]
        reader_markers = [str(item) for item in profile.get("reader_direct_markers", []) if str(item)]
        field_hits = [item for item in field_markers if item in value]
        reader_hits = [item for item in reader_markers if item in value]
        details.update({
            "field_perspective_hits": field_hits,
            "reader_direct_hits": reader_hits,
        })
        if not field_hits:
            reasons.append("voice_scout_field_perspective_missing")
            score -= 20
        if not reader_hits:
            score -= 8
        if not preferred_hits:
            score -= 8
    elif account_id == "liver_manager":
        warm_markers = [str(item) for item in profile.get("warm_markers", []) if str(item)]
        empathy_markers = [str(item) for item in profile.get("empathy_markers", []) if str(item)]
        action_markers = [str(item) for item in profile.get("action_markers", []) if str(item)]
        stereotypes = [str(item) for item in profile.get("forbidden_stereotypes", []) if str(item)]
        warm_hits = [item for item in warm_markers if item in value]
        empathy_hits = [item for item in empathy_markers if item in value]
        action_hits = [item for item in action_markers if item in value]
        stereotype_hits = [item for item in stereotypes if item in value]
        details.update({
            "warm_cadence_hits": warm_hits,
            "empathy_hits": empathy_hits,
            "next_stream_action_hits": action_hits,
            "forbidden_stereotype_hits": stereotype_hits,
        })
        if not warm_hits:
            reasons.append("voice_warm_conversational_cadence_missing")
            score -= 22
        if not action_hits:
            reasons.append("voice_next_stream_action_missing")
            score -= 18
        if not empathy_hits:
            score -= 7
        if stereotype_hits:
            reasons.append("voice_stereotyped_feminine_language")
            score -= 35
    elif account_id == "beauty_account":
        warm_markers = [str(item) for item in profile.get("warm_markers", []) if str(item)]
        beauty_markers = [str(item) for item in profile.get("beauty_markers", []) if str(item)]
        practical_markers = [str(item) for item in profile.get("practical_markers", []) if str(item)]
        stereotypes = [str(item) for item in profile.get("forbidden_stereotypes", []) if str(item)]
        ad_phrases = [str(item) for item in profile.get("forbidden_ad_phrases", []) if str(item)]
        warm_hits = [item for item in warm_markers if item in value]
        beauty_hits = [item for item in beauty_markers if item in value]
        practical_hits = [item for item in practical_markers if item in value]
        stereotype_hits = [item for item in stereotypes if item in value]
        ad_hits = [item for item in ad_phrases if item in value]
        details.update({
            "warm_cadence_hits": warm_hits,
            "beauty_context_hits": beauty_hits,
            "practical_action_hits": practical_hits,
            "forbidden_stereotype_hits": stereotype_hits,
            "forbidden_ad_phrase_hits": ad_hits,
        })
        if not warm_hits:
            reasons.append("voice_beauty_warmth_missing")
            score -= 20
        if not beauty_hits:
            reasons.append("voice_beauty_context_missing")
            score -= 25
        if not practical_hits:
            reasons.append("voice_beauty_practical_action_missing")
            score -= 20
        if stereotype_hits:
            reasons.append("voice_stereotyped_feminine_language")
            score -= 35
        if ad_hits:
            reasons.append("voice_beauty_advertising_phrase_present")
            score -= 40

    formal_penalty = min(100, len(formal_hits) * 25 + (20 if value.count("ください") >= 2 else 0))
    conversational_hits = set(preferred_hits)
    if account_id in {"liver_manager", "beauty_account"}:
        conversational_hits.update(details.get("warm_cadence_hits", []))
    conversational_score = min(100, 55 + len(conversational_hits) * 12)
    feminine_warmth_score = 0
    if account_id in {"liver_manager", "beauty_account"}:
        feminine_warmth_score = min(
            100,
            50
            + len(details.get("warm_cadence_hits", [])) * 10
            + len(details.get("empathy_hits", [])) * 8
            + len(details.get("next_stream_action_hits", [])) * 6
            + len(details.get("beauty_context_hits", [])) * 5
            + len(details.get("practical_action_hits", [])) * 5,
        )
    details.update({
        "formal_consultant_penalty": formal_penalty,
        "conversational_style_score": conversational_score,
        "feminine_warmth_score": feminine_warmth_score,
    })

    minimum_score = int(load_account_voice_profiles().get("semantic_voice_score_min", 85))
    score = max(0, min(100, score))
    if score < minimum_score:
        reasons.append("voice_persona_score_below_threshold")
    reasons = sorted(set(reasons))
    return {
        "status": "VOICE_PERSONA_PASS" if not reasons else "BLOCKED",
        "score": score,
        "minimum_score": minimum_score,
        "reasons": reasons,
        "details": details,
    }


def persona_validation(text: str, account_id: str) -> dict[str, Any]:
    """Validate the reader-facing voice from the central account profile."""
    profiles = load_post_generation_rules().get("persona_profiles", {})
    profile = profiles.get(account_id)
    if not isinstance(profile, dict):
        return {"status": "PASS", "score": 80, "reasons": [], "details": {"profile": "not_configured"}}

    reasons: list[str] = []
    voice = voice_persona_validation(text, account_id)
    reader_terms = [str(term) for term in profile.get("reader_terms", [])]
    reader_hits = [term for term in reader_terms if term in text]
    if len(reader_hits) < int(profile.get("minimum_reader_terms", 1)):
        reasons.append("persona_reader_context_insufficient")
    forbidden_first_person = [str(term) for term in profile.get("forbidden_first_person", [])]
    first_person_mismatches = [term for term in forbidden_first_person if term in text]
    if first_person_mismatches:
        reasons.append("persona_first_person_mismatch")
    blocked_terms = [str(term) for term in profile.get("blocked_terms", [])]
    blocked_hits = [term for term in blocked_terms if term in text]
    if blocked_hits:
        reasons.append("persona_aggressive_recruiting")

    details: dict[str, Any] = {
        "first_person": str(canonical_voice_profile(account_id).get("first_person", profile.get("first_person", ""))),
        "reader_term_count": len(reader_hits),
        "reader_terms": reader_hits,
        "first_person_mismatches": first_person_mismatches,
        "blocked_terms": blocked_hits,
        "voice_persona": voice,
    }
    score = 72 + min(16, len(reader_hits) * 6)

    if account_id == "night_scout":
        decision_hits = [term for term in profile.get("decision_markers", []) if str(term) in text]
        details["decision_marker_count"] = len(decision_hits)
        details["decision_markers"] = decision_hits
        if len(decision_hits) < int(profile.get("minimum_decision_markers", 1)):
            reasons.append("persona_decision_support_missing")
        score += min(10, len(decision_hits) * 4)
    elif account_id == "liver_manager":
        action_hits = [term for term in profile.get("action_markers", []) if str(term) in text]
        if re.search(r"(?:してみ|した方が|すること|できる|見てお|決めてお)", text):
            action_hits.append("action_sentence_structure")
        logic_hits = [term for term in profile.get("logic_markers", []) if str(term) in text]
        if re.search(r"(?:から|ので|ことで|ため|理由|改善|反応|と、|この|だけで|ほど)", text):
            logic_hits.append("logic_sentence_structure")
        manager_hits = [
            term
            for term in profile.get(
                "manager_markers",
                [],
            )
            if str(term) in text
        ]
        soft_hits = [
            term
            for term in profile.get(
                "soft_markers",
                [],
            )
            if str(term) in text
        ]
        raw_emoji_policy = profile.get(
            "emoji_policy",
            {},
        )
        emoji_policy = (
            raw_emoji_policy
            if isinstance(raw_emoji_policy, dict)
            else {}
        )
        allowed_emojis = [
            str(item)
            for item in emoji_policy.get(
                "allowed",
                [],
            )
        ]
        emoji_count = sum(
            text.count(emoji)
            for emoji in allowed_emojis
            if emoji
        )
        emoji_max = int(
            emoji_policy.get(
                "maximum",
                2,
            )
        )
        masculine_endings = sum(
            text.count(str(term))
            for term in profile.get(
                "masculine_endings",
                [],
            )
        )
        fragments = [
            line.strip()
            for line in text.splitlines()
            if (
                line.strip()
                and len(line.strip()) <= 18
                and not re.search(
                    r"[。！？]$",
                    line.strip(),
                )
            )
        ]
        details.update({
            "action_marker_count": len(action_hits),
            "logic_marker_count": len(logic_hits),
            "manager_marker_count": len(manager_hits),
            "soft_marker_count": len(soft_hits),
            "soft_markers": soft_hits,
            "emoji_count": emoji_count,
            "emoji_max": emoji_max,
            "full_stop_count": text.count("。"),
            "full_stop_policy": profile.get(
                "full_stop_policy",
                "",
            ),
            "masculine_ending_count": masculine_endings,
            "short_fragment_count": len(fragments),
        })
        if len(action_hits) < int(
            profile.get(
                "minimum_action_markers",
                1,
            )
        ):
            reasons.append(
                "persona_concrete_action_missing"
            )
        if len(logic_hits) < int(
            profile.get(
                "minimum_logic_markers",
                1,
            )
        ):
            reasons.append(
                "persona_logic_missing"
            )
        if masculine_endings >= 3:
            reasons.append(
                "persona_masculine_assertion_repetition"
            )
        if len(fragments) >= 6:
            reasons.append(
                "persona_fragment_overuse"
            )
        if emoji_count > emoji_max:
            reasons.append(
                "persona_emoji_overuse"
            )
        score += (
            min(7, len(action_hits) * 3)
            + min(7, len(logic_hits) * 3)
            + min(4, len(manager_hits) * 2)
            + min(6, len(soft_hits) * 2)
        )
        score -= masculine_endings * 5
        score -= max(
            0,
            len(fragments) - 5,
        ) * 4
        score -= max(
            0,
            emoji_count - emoji_max,
        ) * 5
    elif account_id == "beauty_account":
        action_hits = [term for term in profile.get("action_markers", []) if str(term) in text]
        details.update({
            "action_marker_count": len(action_hits),
            "action_markers": action_hits,
        })
        if len(action_hits) < int(profile.get("minimum_action_markers", 1)):
            reasons.append("persona_beauty_practical_action_missing")
        score += min(10, len(action_hits) * 4)

    if voice["status"] != "VOICE_PERSONA_PASS":
        reasons.append("voice_persona_not_pass")
        reasons.extend(str(reason) for reason in voice["reasons"])
        score = min(score, int(voice["score"]))
    if first_person_mismatches:
        score -= 35
    if blocked_hits:
        score -= 35
    return {
        "status": "PASS" if not reasons else "BLOCKED",
        "score": max(0, min(100, score)),
        "reasons": sorted(set(reasons)),
        "details": details,
    }


def final_public_post_validator(text: Any, account_id: str = "") -> dict[str, Any]:
    public_text = extract_public_post_text(text)
    reasons: list[str] = []
    internal_hits = _contains_terms(public_text, INTERNAL_LEAK_TERMS)
    metadata_hits = [p for p in SOURCE_METADATA_PATTERNS if re.search(p, public_text, re.IGNORECASE)]
    hashtag_count = len(re.findall(r"(?:^|\s)#\S+", public_text))
    risk = _risk_score(public_text)
    cta = _cta_pressure_score(public_text)
    natural = _naturalness_score(
        public_text,
        account_id,
    )
    reader = _reader_value_score(public_text, account_id)
    persona = persona_validation(public_text, account_id)
    voice = persona.get("details", {}).get("voice_persona", voice_persona_validation(public_text, account_id))
    beauty_compliance = (
        beauty_compliance_validation(public_text)
        if account_id == "beauty_account"
        else {"status": "NOT_APPLICABLE", "requires_human_review": False, "blocked_reasons": []}
    )
    fit = int(persona["score"])
    quality = min(100, int((natural + reader + fit + max(0, 100 - cta) + max(0, 100 - risk)) / 5))

    if internal_hits:
        reasons.append("internal_terms")
    if metadata_hits:
        reasons.append("source_metadata_or_url")
    if "これは投稿案" in public_text or "投稿案です" in public_text:
        reasons.append("draft_label")
    if hashtag_count > 4:
        reasons.append("too_many_hashtags")
    if risk > 10:
        reasons.append("risk_score_above_max")
    if cta > 30:
        reasons.append("cta_pressure_above_max")
    if len(public_text) < 80:
        reasons.append("too_short")
    if len(public_text) > 520:
        reasons.append("too_long")
    if account_id == "beauty_account" and len(public_text) > 320:
        reasons.append("beauty_text_too_long")
    if natural < 80:
        reasons.append("naturalness_below_threshold")
    if reader < 80:
        reasons.append("reader_value_below_threshold")
    if persona["status"] != "PASS" or fit < 80:
        reasons.append("account_fit_below_threshold")
    if voice.get("status") != "VOICE_PERSONA_PASS":
        reasons.append("voice_persona_not_pass")
    if beauty_compliance.get("status") == "BLOCKED":
        reasons.extend(str(reason) for reason in beauty_compliance.get("blocked_reasons", []))
    reasons.extend(persona["reasons"])
    if quality < 85:
        reasons.append("quality_below_threshold")

    return {
        "status": "PASS" if not reasons else "BLOCKED",
        "blocked_reasons": sorted(set(reasons)),
        "public_post_text": public_text,
        "text_length": len(public_text),
        "internal_leak_check": {
            "status": "PASS" if not internal_hits else "BLOCKED",
            "hits": internal_hits,
            "internal_leak_score": len(internal_hits),
        },
        "source_metadata_check": {
            "status": "PASS" if not metadata_hits else "BLOCKED",
            "hits": metadata_hits,
        },
        "account_fit_check": {
            "status": "PASS" if persona["status"] == "PASS" and fit >= 80 else "BLOCKED",
            "account_fit_score": fit,
            "persona": persona,
        },
        "voice_persona_check": voice,
        "beauty_compliance_check": beauty_compliance,
        "requires_human_review": bool(beauty_compliance.get("requires_human_review")),
        "public_post_quality_score": quality,
        "reader_value_score": reader,
        "naturalness_score": natural,
        "account_fit_score": fit,
        "cta_pressure_score": cta,
        "risk_score": risk,
        "similarity_to_source": 0.0,
    }



def apply_account_voice(text: str, account_id: str) -> str:
    """Convert the topic-bearing closing itself; never append a new topic."""

    value = str(text or "").strip()
    if not value:
        return value
    if account_id == "night_scout" and "僕" not in value:
        value = value.replace("確認してください。", "確認した方がいい。")
        value = value.replace("整理してみてください。", "整理してみるのが大事だよ。")
        value = value.replace("見てみてください。", "見てみた方がいい。")
        parts = value.rsplit("\n\n", 1)
        closing = parts[-1]
        if not any(term in closing for term in canonical_voice_profile(account_id).get("preferred_cadence", [])):
            if closing.endswith("したい。"):
                closing = closing[:-1] + "んだよね。"
            elif closing.endswith("大事。"):
                closing = closing[:-3] + "大事だよ。"
            elif closing.endswith("方がいい。"):
                closing = closing[:-1] + "んだよね。"
            else:
                closing = closing.rstrip("。") + "と思うんだよね。"
        parts[-1] = "僕なら、" + closing
        return "\n\n".join(parts)
    if account_id == "liver_manager" and "私" not in value:
        replacements = (
            ("確認してみてください。", "確認してみてね。"),
            ("試してみてください。", "試してみてね。"),
            ("整えてみてください。", "整えてみてね。"),
            ("決めてみてください。", "決めてみてね。"),
            ("してみましょう。", "してみよ。"),
            ("整えましょう。", "整えてみよ。"),
            ("してください。", "してみてね。"),
            ("ください。", "みてね。"),
            ("伝えます。", "伝える。"),
            ("作ります。", "作る。"),
            ("確認します。", "確認する。"),
            ("整えます。", "整える。"),
            ("見直します。", "見直す。"),
            ("決めます。", "決める。"),
            ("できます。", "できるよ。"),
            ("思います。", "思うよ。"),
            ("なります。", "なるよ。"),
        )
        for old, new in replacements:
            value = value.replace(old, new)
        parts = value.rsplit("\n\n", 1)
        closing_source = parts[-1]
        if closing_source.startswith("まずは"):
            closing_source = closing_source[len("まずは"):].lstrip("、 ")
        elif closing_source.startswith("まず、"):
            closing_source = closing_source[len("まず、"):].lstrip()
        closing = "私ならまず、" + closing_source
        warm_markers = canonical_voice_profile(account_id).get("warm_markers", [])
        if not any(term in closing for term in warm_markers):
            ending_replacements = (
                ("変わる。", "変わっていくんだよね。"),
                ("大事。", "大事なんだよね。"),
                ("十分。", "十分なんだよね。"),
                ("強い。", "強いんだよね。"),
                ("いい。", "いいんだよね。"),
                ("なりやすい。", "なりやすいんだよね。"),
                ("続きやすい。", "続きやすいんだよね。"),
                ("安定しやすい。", "安定しやすいんだよね。"),
            )
            for old, new in ending_replacements:
                if closing.endswith(old):
                    closing = closing[: -len(old)] + new
                    break
            else:
                closing = closing.rstrip("。") + "んだよね。"

        action_markers = canonical_voice_profile(account_id).get("action_markers", [])
        if not any(term in value for term in action_markers):
            if "事務所" in value:
                action = "事務所を比べる前に、確認項目を一つだけ書いてみてね。"
            else:
                action_options = (
                    "次の配信では、気になった一つを実際に試してみてね。",
                    "次に配信する時は、ここから一つだけ試してみてね。",
                    "全部変えなくて大丈夫。次の配信で一つだけ試してみよ。",
                    "次の配信で、できそうなことを一つだけ試してみてね。",
                )
                digest = hashlib.sha256(value.encode("utf-8")).hexdigest()
                action = action_options[int(digest[:8], 16) % len(action_options)]
            closing = f"{closing}\n{action}"
        parts[-1] = closing
        return "\n\n".join(parts)
    return value


def generate_reader_facing_post(account_id: str, index: int = 1) -> dict[str, Any]:
    """Deterministic account-specific public text for autonomous text-only posts."""
    if account_id == "liver_manager":
        variants = [
            (
                "配信で伸びない人ほど、最初から面白いことを言おうとしすぎる。\n\n"
                "でも初心者の配信で大事なのは、面白さより入りやすさ。\n\n"
                "入った瞬間に何を話していいかわからない。\n"
                "コメントしても拾われるかわからない。\n"
                "常連だけで盛り上がっていて入りづらい。\n\n"
                "この状態だと、初見はすぐ抜ける。\n\n"
                "まずは、来てくれてありがとう、今この話をしてるよ、気軽にコメントしてねを自然に言えること。\n\n"
                "配信は才能より、入りやすい空気を作れるかが大きい。"
            ),
            (
                "ライバーを始めたいのに動けない人は、配信内容より先に不安を整理した方がいい。\n\n"
                "何を話すか。\n"
                "誰も来なかったらどうするか。\n"
                "コメントが止まったらどうするか。\n"
                "生活リズムに無理がないか。\n\n"
                "ここが曖昧なまま始めると、数回でしんどくなる。\n\n"
                "最初から完璧に話す必要はない。\n"
                "続けられる時間と、初見が入りやすい一言を決めるだけでもかなり変わる。"
            ),
            (
                "配信でコメントが増えない時、話す内容だけを変えても伸びないことがある。\n\n"
                "初見が入りづらい空気だと、どれだけ頑張って話していてもすぐ抜けられる。\n\n"
                "まず見るのは、入室した人に気づけているか。\n"
                "今何の話をしているか伝えているか。\n"
                "コメントしていい雰囲気を作れているか。\n\n"
                "配信は一方的に話す場じゃなくて、入りやすい会話の入口を作る場。\n"
                "ここを整えるだけで、初見の残り方は変わる。"
            ),
            (
                "ライバー事務所を選ぶ時、条件だけで決めるとあとで迷いやすい。\n\n"
                "大事なのは、配信を続けるための相談ができるか。\n"
                "数字が落ちた時に一緒に原因を見てくれるか。\n"
                "自分の生活リズムに合った配信設計を考えてくれるか。\n\n"
                "最初から全部わかっている人はいない。\n"
                "だからこそ、始める前にサポートの中身を確認した方がいい。"
            ),
            (
                "配信を始めたばかりの人ほど、毎回違うことをしようとして疲れやすい。\n\n"
                "でも最初に必要なのは、派手な企画より続けられる型。\n\n"
                "始まりの挨拶。\n"
                "今日話すテーマ。\n"
                "初見への一言。\n"
                "コメントが止まった時の話題。\n\n"
                "この流れがあるだけで、配信中に迷う時間が減る。\n"
                "慣れるまでは才能より、続けやすい型を持つ方が強い。"
            ),
            (
                "配信がしんどくなる人は、数字だけを見すぎていることが多い。\n\n"
                "もちろん結果は大事。\n"
                "でも毎回の視聴者数だけで良し悪しを決めると、続ける気力が削られる。\n\n"
                "今日は初見に挨拶できたか。\n"
                "コメントを拾えたか。\n"
                "次も来やすい空気を作れたか。\n\n"
                "小さい改善を見られる人ほど、配信は続きやすい。"
            ),
            (
                "TikTok LIVEに興味があるなら、最初から完璧なキャラを作らなくていい。\n\n"
                "むしろ無理に盛りすぎると、続けるのがきつくなる。\n\n"
                "話しやすい時間帯。\n"
                "自然に話せるテーマ。\n"
                "初見に返しやすい一言。\n"
                "疲れすぎない配信時間。\n\n"
                "まずはこのあたりを決めるだけで十分。\n"
                "配信は始め方より、続けられる形を作れるかが大事。"
            ),
            (
                "リスナーが定着しない時は、話の面白さより安心感を見直した方がいい。\n\n"
                "コメントしても反応が薄い。\n"
                "内輪だけで盛り上がっている。\n"
                "何を話している配信かわかりにくい。\n\n"
                "この状態だと、初見は残りづらい。\n\n"
                "まずは来てくれた人が入れる余白を作ること。\n"
                "配信は盛り上げる前に、参加しやすくするのが大事。"
            ),
            (
                "配信を伸ばしたいなら、長く話すより反応しやすい話題を置いた方がいい。\n\n"
                "最近ハマっていること。\n"
                "今日あった小さい出来事。\n"
                "二択で答えられる質問。\n"
                "初見でも入れる軽いテーマ。\n\n"
                "コメントは、書きやすい入口があるだけで増えやすい。\n"
                "難しい話をするより、参加しやすい空気を作る方が先。"
            ),
            (
                "配信初心者が最初につまずくのは、話題がないことより一人で抱えすぎること。\n\n"
                "伸びない理由がわからない。\n"
                "どの時間に配信すればいいかわからない。\n"
                "コメントが少ないと不安になる。\n\n"
                "ここを一人で判断し続けると、だんだんしんどくなる。\n\n"
                "最初は配信内容より、振り返り方を作ること。\n"
                "続けられる人は、毎回少しずつ直す場所を見つけている。"
            ),
            (
                "ライバーが配信時間を決める時、空いている時間だけで選ぶと続きにくい。\n\n"
                "眠い時間に無理をする。\n"
                "準備する余裕がない。\n"
                "終わったあとに生活が崩れる。\n"
                "次の日まで疲れが残る。\n\n"
                "続けるには、配信する時間だけじゃなく前後の余白も大事。\n"
                "リスナーに会いやすく、自分も無理なく続けられる時間帯を先に決めた方が安定しやすい。"
            ),
            (
                "ギフトを増やしたい時ほど、お願いの強さより応援したくなる流れを見た方がいい。\n\n"
                "初見が入りやすい。\n"
                "コメントを拾ってもらえる。\n"
                "話していて居場所がある。\n"
                "また来たい理由がある。\n\n"
                "この土台がないままお願いだけ強くすると、見ている側は疲れる。\n"
                "配信は先に関係性を作る方が伸びやすい。"
            ),
            (
                "配信の終わり方が曖昧だと、次も見に来る理由が残りにくい。\n\n"
                "今日来てくれたことへのお礼。\n次に話す予定。\nまたコメントしやすい一言。\n\n"
                "この三つがあるだけで、初見にも常連にも次の入口ができる。\n"
                "最後の数分まで、参加しやすい空気を作ることが大事。"
            ),
            (
                "配信で話題が途切れた時、焦ってずっと話し続けなくていい。\n\n"
                "最近食べたもの。\n今日いちばん困ったこと。\n今週やってみたいこと。\n\n"
                "答えやすい話題を一つ置くと、コメントは入りやすくなる。\n"
                "沈黙を怖がるより、会話の入口を準備しておく方が続けやすい。"
            ),
            (
                "配信を続けるなら、毎回反省を増やしすぎない方がいい。\n\n"
                "初見に挨拶できたか。\nコメントを一つ丁寧に拾えたか。\n次回の話題を一つ決められたか。\n\n"
                "見る場所を絞ると、改善は続けやすい。\n"
                "小さな変化を積み重ねる方が、気持ちも配信も安定しやすい。"
            ),
            (
                "配信前の準備は、機材を増やすことより気持ちに余白を作ること。\n\n"
                "話すテーマを一つ。\n初見への挨拶を一つ。\nコメントが止まった時の質問を一つ。\n\n"
                "これだけ決めておけば、始まってから慌てにくい。\n"
                "続く配信は、準備が完璧だからではなく無理が少ないから続く。"
            ),
            (
                "初見が来た時、すぐに盛り上げようとしなくても大丈夫。\n\n"
                "来てくれたことに気づく。\n今している話を短く伝える。\n気軽に参加できる質問を置く。\n\n"
                "この順番なら、見ているだけの人も入りやすい。\n"
                "配信は最初の一言で、空気がかなり変わる。"
            ),
            (
                "配信の時間を増やしても疲れてしまうなら、回数より設計を見直したい。\n\n"
                "無理なく話せる長さ。\n休める曜日。\n振り返る時間。\n次回の準備に使える余白。\n\n"
                "自分が続けられる形を作ると、配信の質も初見への返し方も保ちやすい。"
            ),
            (
                "コメントが少ない日は、配信が向いていないと決めなくていい。\n\n"
                "入った人に挨拶できたか。\n話題が一方通行になっていないか。\n返しやすい質問を置けたか。\n\n"
                "確認する場所があると、数字だけで気持ちを振り回されにくい。\n"
                "次の配信で一つ試せば十分。"
            ),
            (
                "ライバーを始める前に、誰かのやり方を全部真似する必要はない。\n\n"
                "自分が話しやすいテーマ。\n続けやすい時間。\n無理なく返せるコメントの量。\n\n"
                "ここを自分に合わせる方が、配信は長く続きやすい。\n"
                "最初は自分の話しやすさを見つける時間にしていい。"
            ),
            (
                "配信で常連が増えてきた時ほど、初見が置いていかれないか見ておきたい。\n\n"
                "内輪の話が長くなりすぎない。\n今の話題を時々説明する。\n初めてのコメントも拾う。\n\n"
                "新しく来た人が参加できると、配信全体の空気もやわらかくなる。"
            ),
            (
                "配信が終わったあとに疲れ切ってしまうなら、頑張り方を増やす前に減らせるものを探したい。\n\n"
                "長すぎる配信。\n準備しすぎる企画。\n全部のコメントに完璧に返そうとすること。\n\n"
                "続けるためには、余裕を残すことも大事。\n"
                "無理の少ない形の方が、見ている人にも自然な空気が伝わる。"
            ),
            (
                "ライバー事務所を比べる時は、始める前の説明だけで判断しない方がいい。\n\n"
                "困った時に誰へ聞けるか。\n配信後に振り返れるか。\n自分の生活に合う進め方を考えてくれるか。\n\n"
                "続けるほど迷いは出てくるから、相談のしやすさまで見て選ぶと安心しやすい。"
            ),
            (
                "配信で自信がなくなった時は、他の人の数字だけを見続けない方がいい。\n\n"
                "昨日より挨拶ができた。\n前よりコメントを拾えた。\n終わり方を決められた。\n\n"
                "自分の変化を見つけられると、続ける理由が少しずつ増えていく。\n"
                "配信は一回ごとの完璧さより、続けた中で作る空気が大事。"
            ),
            (
                "初見がコメントしやすい配信は、答えを急がせない。\n\n"
                "好きな食べ物みたいな軽い質問。\n二択で答えられる話題。\n見ているだけでも大丈夫という一言。\n\n"
                "参加のハードルを下げると、会話は少しずつ始まりやすい。\n"
                "気軽に入れる空気を作ることが、次のコメントにつながる。"
            ),
        ]
        text = variants[(index - 1) % len(variants)]
    else:
        variants = [
            (
                "夜職で店を選ぶ時、時給だけで決める子はけっこう危ない。\n\n"
                "時給が高くても、客層が合わない。\n"
                "ノルマがきつい。\n"
                "出勤ペースが合わない。\n"
                "担当に相談しづらい。\n"
                "雰囲気が自分に合わない。\n\n"
                "このどれかがズレると、結局続かない。\n\n"
                "大事なのは、条件が良い店じゃなくて、自分が続けられる店を選ぶこと。\n\n"
                "迷っているなら、入る前に一回整理した方がいい。"
            ),
            (
                "夜職を始める前に見てほしいのは、時給よりも続けられる条件。\n\n"
                "家から遠すぎないか。\n"
                "出勤ペースに無理がないか。\n"
                "客層が自分に合いそうか。\n"
                "困った時に担当へ相談できるか。\n\n"
                "ここを見ないまま入ると、条件は良いのにしんどい店になることがある。\n\n"
                "焦って決めるより、先に自分が無理なく働ける形を整理した方がいい。"
            ),
            (
                "夜職でしんどくなる子は、入店前に確認するポイントが少ないことが多い。\n\n"
                "時給はいくらか。\n"
                "ノルマはあるか。\n"
                "客層は合いそうか。\n"
                "出勤ペースに無理はないか。\n"
                "困った時に誰へ相談できるか。\n\n"
                "ここを曖昧にしたまま入ると、条件が良くても続かないことがある。\n"
                "店選びは勢いより、先に不安を整理する方が大事。"
            ),
            (
                "キャバで働く時、合わない店を選ぶと自分の努力だけではどうにもならないことがある。\n\n"
                "客層が合わない。\n"
                "担当に相談しづらい。\n"
                "出勤の圧が強い。\n"
                "ノルマの感覚が合わない。\n\n"
                "こういうズレは、入ってから気づくとかなりしんどい。\n\n"
                "だから時給だけじゃなく、自分が続けられる環境かを見ること。\n"
                "迷うなら入る前に一度整理した方がいい。"
            ),
            (
                "夜職を副業で考えている子ほど、無理な出勤ペースで決めない方がいい。\n\n"
                "本業の疲れが残る。\n"
                "生活リズムが崩れる。\n"
                "寝不足で接客がきつくなる。\n"
                "続ける前に気持ちが折れる。\n\n"
                "副業で大事なのは、頑張れる店より続けられる店。\n"
                "条件を見る時は、時給と同じくらい自分の生活に合うかを見た方がいい。"
            ),
            (
                "移籍を考える時は、今の店が嫌だからだけで決めるとまた同じことで悩みやすい。\n\n"
                "何が合わなかったのか。\n"
                "客層なのか、担当なのか、ノルマなのか。\n"
                "出勤ペースなのか、店の雰囲気なのか。\n\n"
                "ここを整理しないまま次を選ぶと、条件が変わっても悩みは残る。\n\n"
                "移籍は逃げじゃなくて、合う環境を選び直すこと。\n"
                "だから先に理由をはっきりさせた方がいい。"
            ),
            (
                "夜職で担当に相談しづらい店は、条件が良くても長く続けにくい。\n\n"
                "出勤を増やしたい時。\n"
                "客層が合わない時。\n"
                "ノルマがきつい時。\n"
                "メンタルが落ちている時。\n\n"
                "こういう時に話せる人がいないと、一人で抱え込むことになる。\n\n"
                "店選びでは時給だけじゃなく、困った時に相談できる環境かも見てほしい。"
            ),
            (
                "夜職を始めるか迷っているなら、最初に決めるべきなのは店名より自分の優先順位。\n\n"
                "稼ぎたい金額。\n"
                "出勤できる曜日。\n"
                "避けたい客層。\n"
                "無理したくない条件。\n"
                "相談しやすい担当の有無。\n\n"
                "ここが決まっていないと、条件だけ良く見える店に流されやすい。\n"
                "先に自分の軸を作る方が、あとで後悔しにくい。"
            ),
            (
                "キャバで売上に悩む時、根性だけでどうにかしようとすると苦しくなる。\n\n"
                "客層が合っているか。\n"
                "席で無理しすぎていないか。\n"
                "同伴や指名の流れを作れているか。\n"
                "担当に相談できているか。\n\n"
                "売上は気合いだけじゃなく、環境とやり方で変わる部分がある。\n"
                "一人で抱え込む前に、どこが詰まっているか整理した方がいい。"
            ),
            (
                "夜職で続く子は、最初から強い子ばかりじゃない。\n\n"
                "無理な店を選ばない。\n"
                "合わない条件を我慢しすぎない。\n"
                "困った時に相談する。\n"
                "自分の生活リズムを崩しすぎない。\n\n"
                "このあたりを守っている子の方が、結果的に長く続きやすい。\n\n"
                "強くなるより先に、続けられる環境を選ぶことが大事。"
            ),
            (
                "夜職でお店の空気が合わないと、条件が良くても毎回出勤が重くなる。\n\n"
                "女の子同士の雰囲気。\n"
                "黒服との距離感。\n"
                "お客さんの層。\n"
                "出勤の相談しやすさ。\n\n"
                "このあたりは求人の条件だけでは見えにくい。\n"
                "入る前に、続けられる空気かどうかも見た方がいい。"
            ),
            (
                "夜職で罰金やノルマがきつい店は、時給が高く見えても手元に残りにくいことがある。\n\n"
                "遅刻や欠勤の扱い。\n"
                "同伴や指名の圧。\n"
                "売上が落ちた時の対応。\n"
                "相談できる担当がいるか。\n\n"
                "ここを知らないまま入ると、思ったよりしんどくなる。\n"
                "条件を見る時は、引かれるものまで確認した方がいい。"
            ),
            (
                "夜職をしながら副業や次の仕事を考えるなら、今の働き方を無理に広げすぎない方がいい。\n\n"
                "出勤を増やしすぎる。\n"
                "睡眠を削る。\n"
                "休む時間がなくなる。\n"
                "考える余裕がなくなる。\n\n"
                "将来の選択肢を作るには、今の生活を壊さないことも大事。\n"
                "稼ぎ方と続け方はセットで見た方がいい。"
            ),
            (
                "スカウトを選ぶ時は、紹介できる店の数より話を聞いてくれるかを見た方がいい。\n\n"
                "希望の出勤ペース。\n"
                "苦手な客層。\n"
                "避けたい条件。\n"
                "今の悩み。\n\n"
                "ここを聞かずに店だけ出してくる人だと、入ってからズレやすい。\n"
                "相談しやすさは、店選びと同じくらい大事。"
            ),
            (
                "夜職でメンタルが落ちる時は、自分が弱いからとは限らない。\n\n"
                "客層が合わない。\n"
                "担当に相談できない。\n"
                "ノルマが重い。\n"
                "生活リズムが崩れている。\n\n"
                "環境が合っていないだけで、気持ちが削られることは普通にある。\n"
                "我慢する前に、何がしんどいのか整理した方がいい。"
            ),
            (
                "夜職の体験入店で見るべきなのは、最初に聞いた時給だけじゃない。\n\n"
                "待機中の空気。\n女の子同士の距離感。\n黒服が忙しい時の対応。\n初めてのお客さんにつく時のフォロー。\n\n"
                "短い時間でも、働きやすさは意外と見える。\n"
                "条件と同じくらい、自分が安心して出勤できそうかを見て決めた方がいい。"
            ),
            (
                "夜職を始める時、最初の一ヶ月を頑張りすぎると後から苦しくなりやすい。\n\n"
                "出勤を詰めすぎる。\n慣れない接客で睡眠を削る。\n相談せずに抱え込む。\n\n"
                "最初は環境に慣れることも大事な仕事。\n"
                "無理なく続くペースを作れた子の方が、焦らず次の目標を考えられる。"
            ),
            (
                "夜職でお客さんとの距離感に悩むなら、最初から無理に合わせすぎない方がいい。\n\n"
                "連絡が負担になっていないか。\n自分の生活を崩していないか。\n嫌なことを断れずにいないか。\n\n"
                "接客は頑張るほど大事だけど、続けるための線引きも同じくらい大事。\n"
                "店を選ぶ時は、担当に相談しながら自分が守れる働き方を決めておくと迷いにくい。"
            ),
            (
                "夜職で収入を安定させたいなら、出勤日数だけ増やせばいいわけじゃない。\n\n"
                "自分に合う客層か。\n無理なく話せる接客か。\n休めるペースになっているか。\n相談できる人がいるか。\n\n"
                "続けられる土台がある方が、毎月の波も小さくなりやすい。"
            ),
            (
                "移籍先を探す時は、今の不満を一つずつ言葉にしてから動くと選びやすい。\n\n"
                "出勤のこと。\n客層のこと。\nノルマのこと。\n担当とのやり取りのこと。\n\n"
                "次の店に求めるものがはっきりすると、条件だけで焦って決めにくくなる。"
            ),
            (
                "夜職を副業にするなら、周りが働いている日数をそのまま真似しなくていい。\n\n"
                "本業との両立。\n睡眠の確保。\n急な予定への対応。\n気持ちに余裕が残るか。\n\n"
                "自分の生活を守れる出勤ペースの方が、結局は長く続けやすい。"
            ),
            (
                "夜職で指名が増えない時、会話の上手さだけを責めなくていい。\n\n"
                "お客さんと会える席につけているか。\n自分に合う接客ができる店か。\n次につながる連絡が負担になっていないか。\n\n"
                "やり方と環境が合っていないだけで、苦しくなることはある。\n"
                "一人で結論を急がず、詰まっている場所を見直した方がいい。"
            ),
            (
                "夜職で求人を見る時は、良いことだけが並んでいるほど確認する項目を増やした方がいい。\n\n"
                "出勤の決め方。\nノルマや罰金の扱い。\n客層の傾向。\n困った時の相談先。\n\n"
                "入ってから聞いていなかったとなるより、最初に質問できる方が安心して働ける。"
            ),
            (
                "夜職を続けるか迷う時は、辞めたい気持ちだけで決める前に原因を分けてみてほしい。\n\n"
                "店が合わないのか。\n出勤ペースがきついのか。\n接客に疲れているのか。\n生活リズムが崩れているのか。\n\n"
                "原因が違えば、変えるべきことも違う。\n"
                "自分を責める前に、続け方を選び直す余地がないか見てみるのも大事。"
            ),
            (
                "夜職で相談する相手を選ぶ時は、急かしてくる人より希望を聞いてくれる人を見た方がいい。\n\n"
                "今すぐ決めたいのか。\n避けたい条件はあるか。\n出勤できる日はいつか。\n不安に思っていることは何か。\n\n"
                "ここを飛ばして進めると、あとで無理が出やすい。\n"
                "自分のペースで選べる環境を大事にしてほしい。"
            ),
        ]
        text = variants[(index - 1) % len(variants)]
    text = apply_account_voice(text, account_id)
    persona = persona_validation(text, account_id)

    if account_id == "liver_manager":
        decision_support_repair = (
            "私なら、条件だけで決めずに、"
            "無理なく続けられるかを先に見るかな。"
        )
        concrete_action_repair = (
            "私ならまず、次の配信で"
            "一つだけ試してみるかな。それで大丈夫だよ。"
        )
    else:
        decision_support_repair = (
            "僕なら、条件だけで決めずに"
            "無理なく続けられるかを先に確認するのが大事だよ。"
        )
        concrete_action_repair = (
            "僕が見ている中では、まず避けたい条件を"
            "一つ書き出してから次を選ぶだけでも変わる。"
        )

    if "persona_decision_support_missing" in persona["reasons"]:
        text += f"\n\n{decision_support_repair}"

    if "persona_concrete_action_missing" in persona["reasons"]:
        text += f"\n\n{concrete_action_repair}"

    return build_generation_output(
        internal_analysis=f"account={account_id}; deterministic reader-facing template; index={index}",
        public_post_text=text,
        safety_notes="Public text only. Internal analysis must not be posted.",
        blocked_reasons=[],
    )


def _topic_from_signal(account_id: str, signal: str) -> str:
    """Classify private reference/transcript content without quoting it publicly."""
    text = str(signal or "")
    if account_id == "night_scout":
        # Preserve the production fallback precedence.
        # Transfer synonyms are recognized when a more specific
        # existing category has not already matched.
        mapping = [
            (("時給", "条件", "罰金"), "conditions"),
            (("ノルマ", "売上", "指名"), "pressure"),
            (("客層", "雰囲気", "お店"), "fit"),
            (
                (
                    "移籍",
                    "辞め",
                    "転職",
                    "転身",
                    "移る",
                    "移り",
                ),
                "transfer",
            ),
            (("副業", "出勤", "生活", "睡眠"), "balance"),
        ]
    else:
        # 「コメント」は広すぎるため、具体的な主題を先に判定する。
        mapping = [
            (
                (
                    "ギフト",
                    "応援",
                    "投げ銭",
                    "投げ",
                    "コイン",
                    "バトル",
                    "団結",
                ),
                "support",
            ),
            (("時間", "継続", "習慣"), "consistency"),
            (("企画", "話題", "会話", "二択"), "conversation"),
            (("事務所", "相談", "サポート"), "support_system"),
            (("初見", "入室", "コメント"), "first_viewer"),
        ]
    for words, topic in mapping:
        if any(word in text for word in words):
            return topic
    return "general"


PRODUCTION_COMPONENTS: dict[str, dict[str, dict[str, list[str]]]] = {
    "night_scout": {
        "conditions": {
            "hooks": [
                "求人の時給が高く見えても、実際の手取りは別に確認したい。",
                "夜職の条件を見る時は、表示額より引かれる金額を先に整理したい。",
                "同じ時給でも、控除やバックの仕組みで手元に残る金額は変わる。",
            ],
            "bodies": [
                "ノルマ、罰金、控除、バックの計算方法を分けて聞くと、働いた後の金額を想像しやすい。",
                "体験入店と本入後で条件が変わらないか、曖昧な費用がないかを入店前に質問しておく。",
                "高い数字だけで比べず、提示時給と控除後の手取りまで同じ表に並べて見る。",
            ],
        },
        "pressure": {
            "hooks": [
                "指名や売上が伸びない時、自分の接客だけを原因にしなくていい。",
                "夜職で数字に追われ始めたら、努力量より負担の偏りを確認したい。",
                "頑張っているのに苦しい時は、店の仕組みが自分に合っているかも見直したい。",
            ],
            "bodies": [
                "席につける回数、客層との相性、連絡の負担、担当へ相談できるかを分けると、詰まっている場所が見えやすい。",
                "売上だけを追う前に、無理な出勤や同伴が増えていないか、休める日が残っているかを確かめる。",
                "数字が落ちた理由を接客、環境、出勤ペースに分けると、変えるべきことを選びやすくなる。",
            ],
        },
        "fit": {
            "hooks": [
                "条件が似ている店でも、客層と雰囲気が違えば働きやすさは変わる。",
                "長く続けられる店は、求人票より実際に働く場面を想像して選びたい。",
                "店選びで迷ったら、時給だけでなく自分が自然に接客できる環境かを見たい。",
            ],
            "bodies": [
                "客層、店内の空気、スタッフの対応、出勤相談のしやすさを体験入店で一つずつ確認する。",
                "忙しい時間の雰囲気や女の子同士の距離感まで見ると、毎回の出勤で困りそうな点を想像しやすい。",
                "自分の接客スタイルと店の客層が合うか、担当が希望を聞いてくれるかを判断材料にする。",
            ],
        },
        "transfer": {
            "hooks": [
                "移籍を考えた時は、次の店を探す前に今の不満を分けておきたい。",
                "店を変えても同じ悩みを繰り返さないために、辞めたい理由を言葉にしたい。",
                "夜職の移籍は、条件を上げることより避けたい環境を明確にする方が大事。",
            ],
            "bodies": [
                "客層、出勤の圧、担当との関係、生活への負担を分けると、次の店に求める条件が具体的になる。",
                "今の店で変えられることと、移籍しないと変わらないことを整理してから候補を比べる。",
                "次の店では何を増やしたいか、何を減らしたいかを三つずつ書くと判断しやすい。",
            ],
        },
        "balance": {
            "hooks": [
                "副業で夜職を続けるなら、出勤日数より生活を崩さない設計が先。",
                "稼ぐ予定を増やす時ほど、睡眠と休みを予定表に残しておきたい。",
                "本業と夜職を両立する時は、働ける日ではなく回復できる日から決めたい。",
            ],
            "bodies": [
                "睡眠時間、本業の繁忙日、移動時間まで含めて出勤ペースを決めると、短期間で消耗しにくい。",
                "週の売上目標だけでなく、休む日と帰宅時間の上限も一緒に決めておく。",
                "無理なく続いた週の出勤数を基準にして、忙しい時だけ増やす形の方が調整しやすい。",
            ],
        },
        "general": {
            "hooks": [
                "夜職で迷った時は、不安を一つの悩みとしてまとめない方がいい。",
                "店を決める前に、自分が続けられない条件から整理してみたい。",
                "選択肢が多い時ほど、譲れない基準を少なく決めておくと選びやすい。",
            ],
            "bodies": [
                "条件、客層、出勤、相談先を分けて考えると、自分が本当に確認したい点が見えてくる。",
                "不安なことを質問に変えて担当へ確認すると、入店後の認識違いを減らしやすい。",
                "良い点だけでなく、続ける時に負担になりそうな点も同じように比べる。",
            ],
        },
    },
    "liver_manager": {
        "first_viewer": {
            "hooks": [
                "初見がすぐ抜ける配信は、内容より最初に入りやすい説明があるかを見直したい。",
                "配信の冒頭で今の話題が伝わると、初見は会話へ入りやすくなる。",
                "初見が残る配信は、最初の数秒で何を話しているかがわかりやすい。",
            ],
            "bodies": [
                "入室に気づき、今の話題を一言で伝え、答えやすい質問を置く。だから初見もコメントする理由を作りやすい。",
                "名前を呼ぶ前に配信の状況を短く説明し、二択の質問を置くと会話へ参加しやすい。",
                "冒頭の挨拶、話題の説明、最初の質問を固定すると、毎回の入り口を改善しやすい。",
            ],
        },
        "support": {
            "hooks": [
                "ギフトを増やしたい時ほど、お願いする前に応援したくなる関係を作りたい。",
                "配信の応援は、その場のお願いより次も来たいと思える積み重ねから生まれる。",
                "投げ銭だけを目標にすると、リスナーが参加する理由を見失いやすい。",
            ],
            "bodies": [
                "コメントを丁寧に拾い、常連だけで会話を固めず、初めて来た人にも参加できる余白を作る。",
                "目標を伝える時は、達成したい理由と一緒に楽しめる企画を示すと応援の意味が伝わりやすい。",
                "ギフトの有無に関係なく反応し、次回も話せる話題を残すことで関係を育てていく。",
            ],
        },
        "consistency": {
            "hooks": [
                "ライバーが配信を続けるには、毎回の気合いより休んでも戻れる仕組みが必要。",
                "ライバーが伸び悩む時ほど、長時間配信より続けられる時間帯を固定したい。",
                "継続できるライバーは、配信する日だけでなく休む日も先に決めている。",
            ],
            "bodies": [
                "無理のない開始時間、話しやすいテーマ、終了後の短い振り返りを決める。だから数字が揺れても立て直しやすい。",
                "一週間単位で配信時間と休みを決め、終わった後に良かった点を一つだけ記録する。",
                "長くできた日を基準にせず、疲れている日でも守れる最低ラインから習慣を作る。",
            ],
        },
        "conversation": {
            "hooks": [
                "コメントが少ない時は、面白い話を増やすより答えやすい入口を作りたい。",
                "話題が止まる配信ほど、自由回答ではなく小さな二択が使いやすい。",
                "会話が続く配信は、リスナーが次に何を言えばいいかがわかりやすい。",
            ],
            "bodies": [
                "今日の出来事を短く話し、二択で聞き、返ってきた答えを一つ深掘りする。まずこの流れを試してみる。",
                "質問を連続させず、自分の答えも先に伝えると、リスナーはコメントの例を見つけやすい。",
                "話題を三つ用意するより、一つのコメントから関連する質問を広げる方が自然な会話になりやすい。",
            ],
        },
        "support_system": {
            "hooks": [
                "ライバー事務所を選ぶ時は、所属条件より伸びない時の支え方を確認したい。",
                "配信を始める前に、数字が落ちた時も相談できる事務所かを見ておきたい。",
                "事務所選びでは、案件の多さだけでなく日々の配信改善を誰と進めるかが大事。",
            ],
            "bodies": [
                "生活に合う配信設計、数字の振り返り、困った時の相談方法まで聞く。だから所属後の動きを想像しやすい。",
                "担当者との連絡頻度や改善提案の内容を確認し、自分が必要なサポートと合うかを比べる。",
                "始める時の説明だけでなく、伸び悩んだ時に何を一緒に見直すのかまで質問しておく。",
            ],
        },
        "general": {
            "hooks": [
                "配信が伸びない時は、才能より参加しにくい場所がないかを見直したい。",
                "ライバーとして迷った時は、変えることを一度に増やしすぎない方がいい。",
                "配信改善は、大きな企画より次回に試せる一つの行動へ落とし込みたい。",
            ],
            "bodies": [
                "初見への説明、コメントの拾い方、終わり方を分けて確認し、まず一つだけ変えて反応を見る。",
                "数字が落ちた場面を振り返り、原因の仮説と次に試すことを一つずつ決める。",
                "続けやすさと参加しやすさを分けて考えると、今の配信で直す場所を選びやすい。",
            ],
        },
    },
}

PRODUCTION_CLOSINGS: dict[str, dict[str, list[str]]] = {
    "night_scout": {
        "conditions": [
            "店を比べる時は、表示された時給ではなく控除後の手取りで判断したい。",
            "入店前に費用を質問できるかどうかも、条件を選ぶための大切な確認になる。",
            "最後は、働いた日数ごとに手元へ残る金額を並べて店を決めたい。",
        ],
        "pressure": [
            "数字だけで自分を責めず、どこに負担が偏っているかを担当と整理してみてほしい。",
            "売上を増やす前に、無理な出勤や接客の負担を減らせるか確認したい。",
            "指名の悩みは一人で抱えず、店の環境と接客の両方を見直して決めたい。",
        ],
        "fit": [
            "店を選ぶ時は、条件より自分が自然に接客できる客層かを確認したい。",
            "体験入店では、働く自分を想像できる雰囲気かどうかまで見てほしい。",
            "長く続けるなら、時給と同じくらい店との相性を判断材料にしたい。",
        ],
        "transfer": [
            "移籍先は、今の店で困った理由を繰り返さない条件で選びたい。",
            "次の店へ求めることと避けたいことを整理してから候補を比べてみてほしい。",
            "移籍を急ぐより、辞めたい理由に合った環境かを確認して決めたい。",
        ],
        "balance": [
            "副業と夜職を続けるなら、出勤後も生活を戻せるペースかを確認したい。",
            "休みと睡眠を削らずに守れる出勤数を、自分の基準として決めてほしい。",
            "短期の売上より、翌週も無理なく出勤できる働き方を選びたい。",
        ],
        "general": [
            "不安を質問に変えてから、無理なく続けられる店かを確認したい。",
            "良い点と負担になる点を同じように整理して、自分の基準で選んでほしい。",
            "急いで決めず、毎週続ける姿を想像できる環境かを見てみたい。",
        ],
    },
    "liver_manager": {
        "first_viewer": [
            "次の配信では、初見へ伝える最初の一言を一つ決めて試してみてください。",
            "初見がコメントしやすい入口を一つ整え、配信後に反応を確認してみましょう。",
            "まずは冒頭の説明と質問だけを変えて、初見の滞在がどう変わるか見てください。",
        ],
        "support": [
            "次の配信では、ギフトのお願いよりリスナーとの会話を一つ増やしてみてください。",
            "応援される理由を作るために、コメントへの反応と次回の約束を整えてみましょう。",
            "まずはリスナーがまた参加したくなる会話を一つ残して配信を終えてください。",
        ],
        "consistency": [
            "次の一週間は、ライバーとして守れる配信時間と休む日を先に決めてみてください。",
            "配信後の振り返りを一つだけ残し、続けられるリズムへ少しずつ整えましょう。",
            "長時間できた日ではなく、無理なく継続できた配信を基準にしてみてください。",
        ],
        "conversation": [
            "次の配信では、リスナーが答えやすい質問を一つ決めてコメントの反応を見てください。",
            "まずは一つのコメントを深掘りし、会話が続く流れを試してみましょう。",
            "話題を増やすより、リスナーが参加できる質問の置き方を一つ整えてください。",
        ],
        "support_system": [
            "ライバー事務所を選ぶ時は、配信が伸びない時の相談方法まで確認してください。",
            "所属前に、担当者とどの数字を振り返り、何を改善するのか質問してみましょう。",
            "事務所の説明だけで決めず、ライバーの配信をどう支えるかまで比べてください。",
        ],
        "general": [
            "次の配信では、一つだけ変えてリスナーの反応を確認してみてください。",
            "全部を直そうとせず、まず一番困っている場所から整えてみましょう。",
            "小さく試して配信後に振り返ると、自分に合う改善方法を選びやすくなります。",
        ],
    },
}

QUALITY_TOPIC_MAP: dict[str, dict[str, str]] = {
    "night_scout": {
        "conditions": "work_conditions",
        "pressure": "performance_pressure",
        "fit": "workplace_fit",
        "transfer": "transfer",
        "balance": "schedule_balance",
    },
    "liver_manager": {
        "first_viewer": "first_viewer_retention",
        "support": "community_building",
        "consistency": "continuity",
        "conversation": "comment_activation",
        "support_system": "agency_selection",
    },
}


def generate_grounded_reader_facing_post(
    account_id: str,
    *,
    private_signal: str,
    index: int = 1,
    media_metadata: dict[str, Any] | None = None,
    slot_theme: str = "",
    recent_posts: list[str] | None = None,
    structure_variant: int | None = None,
) -> dict[str, Any]:
    """Build a new public caption from private evidence without exposing it."""
    topic = _topic_from_signal(account_id, private_signal)
    metadata = dict(media_metadata or {})
    recent = [extract_public_post_text(item) for item in (recent_posts or []) if extract_public_post_text(item)]
    seed = hashlib.sha256(
        f"composition_v3|{account_id}|{topic}|{slot_theme}|{private_signal}|{index}".encode("utf-8")
    ).hexdigest()
    choice = int(seed[:12], 16)
    account_components = PRODUCTION_COMPONENTS.get(account_id, {})
    component = account_components.get(topic, account_components.get("general", {}))
    hooks = list(component.get("hooks", []))
    bodies = list(component.get("bodies", []))
    closings = PRODUCTION_CLOSINGS.get(account_id, {}).get(
        topic,
        PRODUCTION_CLOSINGS.get(account_id, {}).get("general", []),
    )
    if not hooks or not bodies or not closings:
        return build_generation_output(
            internal_analysis=f"missing production components account={account_id}; topic={topic}",
            public_post_text="",
            safety_notes="",
            blocked_reasons=["GENERATION_COMPONENTS_UNAVAILABLE"],
        )

    hook = hooks[choice % len(hooks)]
    body = bodies[(choice // max(1, len(hooks))) % len(bodies)]
    closing = closings[(choice // max(1, len(hooks) * len(bodies))) % len(closings)]
    structure = (
        int(structure_variant) % 6
        if structure_variant is not None
        else (choice // max(1, len(hooks) * len(bodies) * len(closings))) % 6
    )
    body_parts = [part.strip() for part in body.split("。") if part.strip()]
    if structure == 0:
        text = f"{hook}\n\n{body}\n\n{closing}"
    elif structure == 1:
        closing_lead = "" if closing.lstrip().startswith(("最後", "まず", "次に")) else "最後に、"
        text = f"{hook}\n\nまず、{body}\n\n{closing_lead}{closing}"
    elif structure == 2:
        if len(body_parts) >= 2:
            text = f"{hook}\n\n{body_parts[0]}。\n\n{body_parts[1]}。\n\n{closing}"
        else:
            text = f"{hook}\n\n確認することは一つ。\n\n{body}\n\n{closing}"
    elif structure == 3:
        text = f"{hook}\n\n見るポイントは次の通り。\n・{body}\n\n{closing}"
    elif structure == 4:
        text = f"{hook}\n\n{body}\n\n次に試すこと：\n{closing}"
    else:
        text = f"{hook}\n\n{body}\n\nこの順番で考える理由はシンプル。\n{closing}"

    text = apply_account_voice(text, account_id)

    concepts = {
        "night_scout": {
            "conditions": ["compensation", "work_conditions", "take_home_pay"],
            "pressure": ["performance_pressure", "support", "workload"],
            "fit": ["customers", "workplace_fit", "consultation"],
            "transfer": ["transfer", "decision_criteria", "fit"],
            "balance": ["side_job", "sleep", "sustainable_schedule"],
            "general": ["anxiety", "decision_criteria", "sustainability"],
        },
        "liver_manager": {
            "first_viewer": ["first_viewer", "participation", "comments"],
            "support": ["community", "support", "retention"],
            "consistency": ["schedule", "reflection", "sustainability"],
            "conversation": ["conversation", "questions", "participation"],
            "support_system": ["agency_selection", "consultation", "improvement"],
            "general": ["entry_experience", "comments", "retention"],
        },
    }
    source_similarity = round(difflib.SequenceMatcher(None, str(private_signal or ""), text).ratio(), 4)
    recent_similarity = round(max((difflib.SequenceMatcher(None, item, text).ratio() for item in recent), default=0.0), 4)
    validation = final_public_post_validator(text, account_id)
    output = build_generation_output(
        internal_analysis=f"grounded topic={topic}; account={account_id}; composition_v3={choice % 54}",
        public_post_text=text,
        safety_notes="Private evidence was reduced to safe concepts. Raw evidence and identifiers are excluded.",
        blocked_reasons=validation.get("blocked_reasons", []),
    )
    quality_topic = QUALITY_TOPIC_MAP.get(account_id, {}).get(topic, "")
    topic_concepts = concepts.get(account_id, {}).get(
        topic,
        concepts.get(account_id, {}).get("general", []),
    )
    cta_intent = "decision_support" if account_id == "night_scout" else "small_next_action"
    post_design = {
        "design_version": "post_design_v1",
        "feature_schema_version": "post_features_v1",
        "account_id": account_id,
        "content_type": str(slot_theme or "general"),
        "source_topic": topic,
        "primary_topic": quality_topic,
        "supporting_concepts": topic_concepts,
        "hook_text": hook,
        "body_text": body,
        "closing_text": closing,
        "key_claims": [hook, body, closing],
        "cta_intent": cta_intent,
        "structure_variant": str(structure),
    }
    output.update({
        "grounding_summary": {
            "topic": topic,
            "quality_topic": quality_topic,
            "concepts": topic_concepts,
            "signal_length_bucket": "long" if len(str(private_signal or "")) >= 400 else "medium" if len(str(private_signal or "")) >= 120 else "short",
            "media_type": str(metadata.get("media_type", "unknown")),
            "slot_theme": str(slot_theme or "general"),
            "structure_variant": structure,
        },
        "post_design": post_design,
        "feature_schema_version": post_design["feature_schema_version"],
        "hook_text": hook,
        "body_text": body,
        "closing_text": closing,
        "key_claims": list(post_design["key_claims"]),
        "cta_intent": cta_intent,
        "transformation_summary": "abstracted concepts, recomposed distinct hook, body, structure and reader action",
        "similarity_score": source_similarity,
        "recent_post_similarity_score": recent_similarity,
        "validator_result": validation["status"],
    })
    return output


def generate_production_post(
    account_id: str,
    *,
    batch_id: str,
    content_type: str,
    recent_posts: list[str] | None = None,
    reference_signal: str = "",
    learning_rule: str = "",
    attempt: int = 0,
    excluded_topics: list[str] | None = None,
    preferred_topics: list[str] | None = None,
) -> dict[str, Any]:
    """Compose a fresh reader-facing post through the shared production path."""
    if str(__import__("os").environ.get("DISABLE_GENERATION_PROVIDER", "")).lower() in {"1", "true", "yes"}:
        return build_generation_output(
            internal_analysis="generation provider disabled",
            public_post_text="",
            safety_notes="",
            blocked_reasons=["GENERATION_PROVIDER_UNAVAILABLE"],
        )
    signals = {
        "night_scout": [
            "時給と控除を含めた条件を比べて手取りを確認する",
            "移籍前に今の店を辞めたい理由と次の店で避けたい条件を整理する",
            "指名や売上に悩む時は接客だけでなく負担の偏りを見直す",
            "夜職と副業を両立するために睡眠と休みを残せる出勤ペースを決める",
            "客層や店の雰囲気が自分の接客と合うか体験入店で確認する",
            "ノルマや罰金、バックの条件を入店前に質問する",
        ],
        "liver_manager": [
            "初見が入りやすい挨拶とコメントの入口を作る",
            "配信時間と休む時間を決めて無理なく継続できるリズムを作る",
            "話題が止まる時は二択や小さな出来事を置いてコメントしやすくする",
            "ライバー事務所を選ぶ時は数字が落ちた時にも相談できる支え方を確認する",
            "ギフトを増やす前にコメントを拾ってリスナーとの関係を作る",
        ],
    }
    if account_id not in signals:
        return build_generation_output(
            internal_analysis=f"unsupported account={account_id}",
            public_post_text="",
            safety_notes="",
            blocked_reasons=["GENERATION_ACCOUNT_UNSUPPORTED"],
        )
    base_digest = hashlib.sha256(
        f"production_composition_v3|{account_id}|{batch_id}|{content_type}|{reference_signal}|{learning_rule}".encode("utf-8")
    ).hexdigest()
    base_choice = int(base_digest[:12], 16)
    signal_values = signals[account_id]
    excluded = {str(value) for value in (excluded_topics or []) if str(value)}
    eligible_signals = [
        signal for signal in signal_values
        if QUALITY_TOPIC_MAP.get(account_id, {}).get(_topic_from_signal(account_id, signal), "") not in excluded
    ]
    if not eligible_signals:
        eligible_signals = signal_values
    preferred = [str(value) for value in (preferred_topics or []) if str(value)]
    preferred_signals = [
        signal for topic in preferred
        for signal in eligible_signals
        if QUALITY_TOPIC_MAP.get(account_id, {}).get(_topic_from_signal(account_id, signal), "") == topic
    ]
    # Four of five deterministic choices exploit measured strategy; one remains
    # exploration so the system can detect drift and discover better topics.
    policy_mode = "explore"
    selection_pool = eligible_signals
    if preferred_signals and base_choice % 5 != 0:
        selection_pool = preferred_signals
        policy_mode = "bounded_exploit"
    private_signal = reference_signal.strip() or selection_pool[(base_choice + attempt) % len(selection_pool)]
    composition_index = base_choice + (attempt * 104729)
    selected_structure_variant = (base_choice + attempt) % 6
    output = generate_grounded_reader_facing_post(
        account_id,
        private_signal=private_signal,
        index=composition_index,
        slot_theme=content_type,
        recent_posts=recent_posts or [],
        structure_variant=selected_structure_variant,
    )
    text = str(output.get("public_post_text", ""))
    if not text:
        output.setdefault("blocked_reasons", []).append("GENERATION_EMPTY_TEXT")
        return output

    output["public_post_text"] = text
    from generation_quality_gates import evaluate_generation_quality
    quality_topic = str(output.get("grounding_summary", {}).get("quality_topic", ""))
    quality = evaluate_generation_quality(
        account_id,
        text,
        recent_posts or [],
        structure_variant=output.get("grounding_summary", {}).get("structure_variant", ""),
        primary_topic=quality_topic,
    )
    output["blocked_reasons"] = final_public_post_validator(text, account_id).get("blocked_reasons", [])
    if quality["status"] != "PASS":
        output["blocked_reasons"].append("GENERATION_QUALITY_BLOCKED")
    output["generation_quality"] = quality
    output["generation_provider"] = "local_composition_v3"
    output["generation_provider_version"] = "3"
    output["generation_batch_id"] = batch_id
    output["generation_attempt"] = attempt + 1
    output["generation_rule_version"] = "production_composition_v3"
    output["generation_policy"] = {
        "policy_version": "bounded_strategy_v1",
        "mode": policy_mode,
        "preferred_topics": preferred,
        "exploration_rate": 0.20,
        "selected_primary_topic": quality_topic,
    }
    output["content_type"] = content_type
    return output

def reader_facing_template_count(account_id: str) -> int:
    """Number of deterministic public templates available for fallback rotation."""
    return 25


def independent_account_order(accounts: list[str]) -> dict[str, Any]:
    """Keep account execution independent; posting history never reorders accounts."""
    return {
        "enabled": True,
        "strategy": "independent_account_runs",
        "ordered_accounts": list(accounts),
        "selected_account": accounts[0] if len(accounts) == 1 else "",
        "skipped_accounts": [],
        "cross_account_rotation": False,
    }


def public_preview(text: str, limit: int = 260) -> str:
    text = extract_public_post_text(text).strip()
    return text if len(text) <= limit else text[:limit].rstrip() + "..."
