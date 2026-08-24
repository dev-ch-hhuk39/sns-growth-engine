"""Deterministic production/canary generation quality gates.

The module is intentionally side-effect free: it never publishes, uploads, or
mutates Sheets. Production and canary generation must call the same functions.
"""
from __future__ import annotations

import re
import sys
from collections import Counter
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from accounts.managed_accounts import managed_account
from generation.semantic_alignment import lexical_similarity

FULL_TEXT_SIMILARITY_MAX = 0.82
HOOK_SIMILARITY_MAX = 0.88
CLOSING_SIMILARITY_MAX = 0.88
STRUCTURE_SIMILARITY_MAX = 0.92
TOPIC_CONFIDENCE_MIN = 0.70
PREFERRED_TOPIC_SCORE_RATIO_MIN = 0.50
SHARED_SENTENCE_MIN_CHARS = 18
QUALITY_GATE_VERSION = "generation_quality_v3"

TOPIC_TAXONOMY: dict[str, dict[str, tuple[str, ...]]] = {
    "night_scout": {
        "work_conditions": ("時給", "控除", "ノルマ", "罰金", "条件", "手取り", "バック", "表示額", "引かれる金額", "提示時給", "費用", "手元へ残る", "働いた日数"),
        "workplace_fit": ("客層", "雰囲気", "店選び", "お店", "店舗", "相性", "働く場面", "求人票", "体験入店", "自然に接客"),
        "transfer": ("移籍", "転職", "辞め", "次の店", "店を変え"),
        "schedule_balance": ("出勤", "副業", "睡眠", "生活", "休み", "休む日", "帰宅時間", "ペース", "両立", "生活を崩", "翌週"),
        "support_system": ("担当", "相談", "サポート", "支え", "環境"),
        "performance_pressure": ("売上", "指名", "同伴", "プレッシャー", "負担", "苦しい", "頑張って", "追われ", "努力量"),
    },
    "liver_manager": {
        "first_viewer_retention": ("初見", "入室", "最初の数秒", "挨拶", "入りやす"),
        "comment_activation": ("コメント", "会話", "質問", "話題", "参加", "声かけ", "二択", "答えやすい"),
        "agency_selection": ("事務所", "所属先", "所属前", "所属条件", "事務所選び", "条件より", "選ぶ"),
        "creator_support": ("相談", "サポート", "支え", "一緒に", "改善を考え"),
        "continuity": ("配信時間", "継続", "習慣", "休む", "リズム", "続けられ", "続ける", "戻れる", "毎回の気合い", "長時間"),
        "monetization": ("ギフト", "投げ銭", "収益", "ダイヤ"),
        "community_building": (
            "リスナー",
            "常連",
            "また来",
            "関係",
            "応援",
            "みんなで支え",
            "皆んなで支え",
            "皆で支え",
            "枠を支え",
            "枠が崩れ",
            "リスナーがついて",
        ),
        "stream_review": ("振り返り", "数字", "改善", "見直"),
        "stream_planning": ("企画", "構成", "終わり方", "配信設計"),
    },
}

RELATED_TOPICS: dict[str, dict[str, set[str]]] = {
    "night_scout": {
        "work_conditions": {"workplace_fit", "support_system"},
        "workplace_fit": {"work_conditions", "support_system", "transfer"},
        "transfer": {"workplace_fit", "support_system", "schedule_balance"},
        "schedule_balance": {"work_conditions", "support_system"},
        "support_system": {"work_conditions", "workplace_fit", "transfer", "schedule_balance", "performance_pressure"},
        "performance_pressure": {"support_system", "workplace_fit"},
    },
    "liver_manager": {
        "first_viewer_retention": {
            "comment_activation",
            "community_building",
        },
        "comment_activation": {"first_viewer_retention", "community_building"},
        "agency_selection": {"creator_support"},
        "creator_support": {"agency_selection", "stream_review", "stream_planning"},
        "continuity": {"stream_planning", "stream_review"},
        "monetization": {"community_building"},
        "community_building": {
            "comment_activation",
            "first_viewer_retention",
            "monetization",
        },
        "stream_review": {"creator_support", "continuity", "stream_planning"},
        "stream_planning": {"creator_support", "continuity", "stream_review"},
    },
}


def _configured_topic_policy(account_id: str) -> tuple[dict[str, tuple[str, ...]], dict[str, set[str]]]:
    record = managed_account(account_id)
    config = __import__("json").loads((ROOT / str(record["account_config"])).read_text(encoding="utf-8"))
    generation = config.get("generation", {})
    raw_taxonomy = generation.get("topic_taxonomy", {}) if isinstance(generation, dict) else {}
    raw_related = generation.get("related_topics", {}) if isinstance(generation, dict) else {}
    taxonomy = {
        str(topic): tuple(str(term) for term in terms if str(term))
        for topic, terms in raw_taxonomy.items()
        if isinstance(terms, list)
    }
    related = {
        str(topic): {str(value) for value in values if str(value)}
        for topic, values in raw_related.items()
        if isinstance(values, list)
    }
    return taxonomy, related


def _topic_taxonomy(account_id: str) -> dict[str, tuple[str, ...]]:
    configured, _ = _configured_topic_policy(account_id)
    return configured or TOPIC_TAXONOMY.get(account_id, {})


def _related_topics(account_id: str) -> dict[str, set[str]]:
    _, configured = _configured_topic_policy(account_id)
    return configured or RELATED_TOPICS.get(account_id, {})


def _sentences(text: str, *, minimum: int = 1) -> list[str]:
    return [
        part.strip()
        for part in re.split(r"[。！？!?\n]+", str(text or ""))
        if len(part.strip()) >= minimum
    ]


def _normalize(text: str) -> str:
    value = re.sub(r"[\s、，。．！？!?・:：;；\-—_()（）「」『』【】\[\]]+", "", str(text or "")).lower()
    previous = None
    while previous != value:
        previous = value
        value = re.sub(
            r"(?:です|ます|でした|ました|でしょう|だと思います|と思います|してみてください|してみたい|してほしい|した方がいい|しておきたい|だ|する|した|なる|い)$",
            "",
            value,
        )
    return value


def _similarity(left: str, right: str) -> float:
    compact_left, compact_right = _normalize(left), _normalize(right)
    if not compact_left or not compact_right:
        return 0.0
    return round(max(lexical_similarity(left, right), SequenceMatcher(None, compact_left, compact_right).ratio()), 4)


def _candidate_text(item: dict[str, Any] | str) -> str:
    if isinstance(item, str):
        return item
    return str(item.get("public_post_text") or item.get("posted_text") or item.get("text") or "")


def _candidate_id(item: dict[str, Any] | str) -> str:
    if isinstance(item, str):
        return ""
    return str(item.get("queue_id") or item.get("canary_id") or item.get("result_id") or item.get("candidate_id") or "")


def _candidate_structure_variant(item: dict[str, Any] | str) -> str:
    if isinstance(item, str):
        return ""
    direct = item.get("structure_variant")
    if direct not in {None, ""}:
        return str(direct)
    grounding = item.get("grounding_summary")
    if isinstance(grounding, dict) and grounding.get("structure_variant") not in {None, ""}:
        return str(grounding.get("structure_variant"))
    generation = item.get("generation")
    if isinstance(generation, dict):
        nested = generation.get("grounding_summary")
        if isinstance(nested, dict) and nested.get("structure_variant") not in {None, ""}:
            return str(nested.get("structure_variant"))
    return ""


def _same_account(account_id: str, item: dict[str, Any] | str) -> bool:
    if isinstance(item, str):
        return True
    item_account = str(item.get("account_id") or item.get("target_account_id") or account_id)
    return item_account == account_id


def _structure_signature(text: str) -> str:
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", str(text or "")) if part.strip()]
    sentences = _sentences(text)
    buckets = []
    for sentence in sentences:
        length = len(_normalize(sentence))
        buckets.append("S" if length < 24 else "M" if length < 48 else "L")
    markers = [
        f"p{len(paragraphs)}",
        f"s{len(sentences)}",
        "q1" if re.search(r"[？?]", text) else "q0",
        "list1" if re.search(r"(?:^|\n)\s*(?:[-・●]|\d+[.)])", text) else "list0",
        "colon1" if re.search(r"[:：]", text) else "colon0",
        "lens:" + "".join(buckets),
    ]
    return "|".join(markers)


def _topic_scores(account_id: str, text: str) -> Counter[str]:
    taxonomy = _topic_taxonomy(account_id)
    normalized = str(text or "")
    scores: Counter[str] = Counter()
    for topic, terms in taxonomy.items():
        for term in terms:
            occurrences = normalized.count(term)
            if occurrences:
                scores[topic] += occurrences * (2 if len(term) >= 4 else 1)
    return scores


def _infer_topic(
    account_id: str,
    text: str,
    *,
    preferred_topic: str = "",
) -> tuple[str, float, list[str]]:
    scores = _topic_scores(account_id, text)
    if not scores:
        return "general", 0.0, []
    ranked = scores.most_common()
    top_topic, top_score = ranked[0]
    selected = top_topic
    preferred_score = scores.get(preferred_topic, 0)
    if preferred_score and preferred_score >= top_score * PREFERRED_TOPIC_SCORE_RATIO_MIN:
        selected = preferred_topic
    total = sum(scores.values())
    confidence = round(scores.get(selected, 0) / max(1, total), 4)
    supporting = [topic for topic, score in ranked if topic != selected and score > 0]
    return selected, confidence, supporting


def _topic_allowed(account_id: str, primary: str, other: str) -> bool:
    return other in {"", "general", primary} or other in _related_topics(account_id).get(primary, set())


def batch_diversity_validator(
    account_id: str,
    text: str,
    compared: Iterable[dict[str, Any] | str],
    *,
    batch_compared: Iterable[dict[str, Any] | str] | None = None,
    structure_variant: str | int = "",
) -> dict[str, Any]:
    mine = _sentences(text, minimum=8)
    my_hook = mine[0] if mine else ""
    my_closing = mine[-1] if mine else ""
    my_structure = _structure_signature(text)
    my_structure_variant = str(structure_variant) if structure_variant not in {None, ""} else ""

    shared_sentences: set[str] = set()
    compared_ids: set[str] = set()
    structure_compared_ids: set[str] = set()
    shared_hook = False
    shared_closing = False
    max_full_similarity = 0.0
    max_hook_similarity = 0.0
    max_closing_similarity = 0.0
    max_structure_similarity = 0.0

    for item in compared:
        if not _same_account(account_id, item):
            continue
        other_text = _candidate_text(item).strip()
        if not other_text:
            continue
        ident = _candidate_id(item)
        if ident:
            compared_ids.add(ident)
        other_sentences = _sentences(other_text, minimum=8)
        other_hook = other_sentences[0] if other_sentences else ""
        other_closing = other_sentences[-1] if other_sentences else ""

        for sentence in mine:
            normalized = _normalize(sentence)
            if len(normalized) < SHARED_SENTENCE_MIN_CHARS:
                continue
            if any(normalized == _normalize(other) for other in other_sentences):
                shared_sentences.add(sentence)

        full_similarity = _similarity(text, other_text)
        hook_similarity = _similarity(my_hook, other_hook)
        closing_similarity = _similarity(my_closing, other_closing)
        max_full_similarity = max(max_full_similarity, full_similarity)
        max_hook_similarity = max(max_hook_similarity, hook_similarity)
        max_closing_similarity = max(max_closing_similarity, closing_similarity)

        shared_hook = shared_hook or bool(
            my_hook and len(_normalize(my_hook)) >= 16 and hook_similarity >= HOOK_SIMILARITY_MAX
        )
        shared_closing = shared_closing or bool(
            my_closing and len(_normalize(my_closing)) >= 16 and closing_similarity >= CLOSING_SIMILARITY_MAX
        )

    # Structural repetition is a batch-level contract. Historical posts can
    # legitimately share a broad three-part format, so structure is compared
    # only with sibling candidates generated in the current batch.
    for item in batch_compared or []:
        if not _same_account(account_id, item):
            continue
        other_text = _candidate_text(item).strip()
        if not other_text:
            continue
        ident = _candidate_id(item)
        if ident:
            structure_compared_ids.add(ident)
        other_structure_variant = _candidate_structure_variant(item)
        if my_structure_variant and other_structure_variant:
            structure_similarity = 1.0 if my_structure_variant == other_structure_variant else 0.0
        else:
            structure_similarity = SequenceMatcher(
                None,
                my_structure,
                _structure_signature(other_text),
            ).ratio()
        max_structure_similarity = max(max_structure_similarity, structure_similarity)

    reasons: list[str] = []
    if shared_sentences:
        reasons.append("shared_sentence")
    if shared_closing:
        reasons.append("shared_closing")
    if shared_hook:
        reasons.append("shared_hook")
    if max_full_similarity >= FULL_TEXT_SIMILARITY_MAX:
        reasons.append("batch_similarity_above_threshold")
    if max_structure_similarity >= STRUCTURE_SIMILARITY_MAX:
        reasons.append("batch_structure_reused")

    return {
        "batch_diversity_status": "PASS" if not reasons else "BLOCKED",
        "batch_similarity_score": round(max_full_similarity, 4),
        "hook_similarity_score": round(max_hook_similarity, 4),
        "closing_similarity_score": round(max_closing_similarity, 4),
        "structure_variant": my_structure_variant,
        "structure_similarity_score": round(max_structure_similarity, 4),
        "shared_sentence_count": len(shared_sentences),
        "shared_sentences": sorted(shared_sentences),
        "shared_closing_detected": shared_closing,
        "shared_hook_detected": shared_hook,
        "compared_candidate_ids": sorted(compared_ids),
        "structure_compared_candidate_ids": sorted(structure_compared_ids),
        "diversity_blocked_reasons": reasons,
    }


def topic_coherence_validator(
    account_id: str,
    text: str,
    *,
    visual_text: str = "",
    primary_topic: str = "",
) -> dict[str, Any]:
    sentences = _sentences(text, minimum=8)
    inferred_primary, inferred_confidence, inferred_supporting = _infer_topic(account_id, text)
    primary = primary_topic.strip() or inferred_primary
    taxonomy = _topic_taxonomy(account_id)
    scores = _topic_scores(account_id, text)
    total_score = sum(scores.values())
    primary_score = scores.get(primary, 0)
    related = _related_topics(account_id).get(primary, set())
    family_score = primary_score + sum(scores.get(topic, 0) for topic in related)
    confidence = round(family_score / max(1, total_score), 4)
    direct_confidence = round(primary_score / max(1, total_score), 4)

    reasons: list[str] = []
    if primary not in taxonomy:
        reasons.append("primary_topic_unresolved")
    elif primary_score <= 0:
        reasons.append("primary_topic_missing_evidence")
    elif confidence < TOPIC_CONFIDENCE_MIN:
        reasons.append("primary_topic_confidence_below_threshold")

    labels: list[str] = []
    off_topic_sentences: list[str] = []
    for sentence in sentences:
        label, sentence_confidence, _ = _infer_topic(
            account_id,
            sentence,
            preferred_topic=primary,
        )
        labels.append(label)
        if sentence_confidence >= 0.5 and not _topic_allowed(account_id, primary, label):
            off_topic_sentences.append(sentence)

    hook_topic = labels[0] if labels else "general"
    closing_topic = labels[-1] if labels else "general"
    hook_match = hook_topic == primary
    closing_match = closing_topic == primary
    if not hook_match:
        reasons.append("hook_topic_mismatch")
    if not closing_match:
        reasons.append("conclusion_topic_mismatch")
    if off_topic_sentences:
        reasons.append("multiple_primary_topics")

    visual_topic = "general"
    visual_confidence = 0.0
    visual_direct_confidence = 0.0
    visual_match = True
    if visual_text.strip():
        visual_topic, _visual_inferred_confidence, _ = _infer_topic(
            account_id,
            visual_text,
            preferred_topic=primary,
        )
        visual_scores = _topic_scores(
            account_id,
            visual_text,
        )
        visual_total_score = sum(
            visual_scores.values()
        )
        visual_primary_score = visual_scores.get(
            primary,
            0,
        )
        visual_related = _related_topics(account_id).get(
            primary,
            set(),
        )
        visual_family_score = (
            visual_primary_score
            + sum(
                visual_scores.get(topic, 0)
                for topic in visual_related
            )
        )
        visual_confidence = round(
            visual_family_score
            / max(1, visual_total_score),
            4,
        )
        visual_direct_confidence = round(
            visual_primary_score
            / max(1, visual_total_score),
            4,
        )
        visual_match = (
            visual_confidence
            >= TOPIC_CONFIDENCE_MIN
            and _topic_allowed(
                account_id,
                primary,
                visual_topic,
            )
        )
        if not visual_match:
            reasons.append("media_text_topic_mismatch")

    score = 100
    score -= 50 if "primary_topic_unresolved" in reasons else 0
    score -= 40 if "primary_topic_missing_evidence" in reasons else 0
    score -= 20 if "primary_topic_confidence_below_threshold" in reasons else 0
    score -= min(45, len(off_topic_sentences) * 25)
    score -= 20 if "hook_topic_mismatch" in reasons else 0
    score -= 25 if "conclusion_topic_mismatch" in reasons else 0
    score -= 30 if "media_text_topic_mismatch" in reasons else 0
    score = max(0, score)

    supporting_topics = sorted({
        label for label in labels + inferred_supporting
        if label not in {"general", primary} and _topic_allowed(account_id, primary, label)
    })
    return {
        "primary_topic": primary,
        "supporting_topics": supporting_topics,
        "topic_confidence": confidence if primary in taxonomy else inferred_confidence,
        "primary_topic_evidence_score": primary_score,
        "primary_topic_direct_confidence": direct_confidence,
        "topic_coherence_status": "PASS" if not reasons else "BLOCKED",
        "topic_coherence_score": score,
        "off_topic_sentence_count": len(off_topic_sentences),
        "off_topic_sentences": off_topic_sentences,
        "hook_topic": hook_topic,
        "closing_topic": closing_topic,
        "visual_topic": visual_topic,
        "visual_topic_confidence": visual_confidence,
        "visual_topic_direct_confidence": (
            visual_direct_confidence
        ),
        "hook_topic_match": hook_match,
        "closing_topic_match": closing_match,
        "visual_topic_match": visual_match,
        "topic_blocked_reasons": reasons,
    }



def persisted_quality_evidence(result: dict[str, Any]) -> dict[str, Any]:
    """Return auditable gate fields without overwriting queue lifecycle status."""
    return {key: value for key, value in result.items() if key != "status"}

def evaluate_generation_quality(
    account_id: str,
    text: str,
    compared: Iterable[dict[str, Any] | str],
    *,
    batch_compared: Iterable[dict[str, Any] | str] | None = None,
    structure_variant: str | int = "",
    visual_text: str = "",
    primary_topic: str = "",
) -> dict[str, Any]:
    diversity = batch_diversity_validator(
        account_id,
        text,
        compared,
        batch_compared=batch_compared,
        structure_variant=structure_variant,
    )
    coherence = topic_coherence_validator(
        account_id,
        text,
        visual_text=visual_text,
        primary_topic=primary_topic,
    )
    passed = diversity["batch_diversity_status"] == "PASS" and coherence["topic_coherence_status"] == "PASS"
    return {
        **diversity,
        **coherence,
        "quality_gate_version": QUALITY_GATE_VERSION,
        "status": "PASS" if passed else "BLOCKED",
    }
