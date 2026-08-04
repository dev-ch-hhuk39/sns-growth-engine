#!/usr/bin/env python3
"""Deterministic reader-context captions grounded in one exact transcript window."""
from __future__ import annotations

import hashlib
import re
from typing import Any

from generation.semantic_alignment import LocalSemanticAlignmentProvider
from generation_quality_gates import evaluate_generation_quality
from media_activation_source_suitability import clip_source_suitability
from public_post_quality import final_public_post_validator

PROVIDER_NAME = "deterministic_evidence_context"
PROVIDER_VERSION = "1"

TOPIC_TERMS: dict[str, dict[str, tuple[str, ...]]] = {
    "night_scout": {
        "work_conditions": ("時給", "条件", "手取り", "バック", "控除", "ノルマ", "罰金"),
        "workplace_fit": ("店選び", "お店", "店舗", "客層", "体験入店", "雰囲気", "相性"),
        "transfer": ("移籍", "次の店", "店を変え", "辞め", "転職"),
        "schedule_balance": ("出勤", "副業", "睡眠", "生活", "両立", "休み"),
        "support_system": ("担当", "相談", "サポート", "環境", "支え"),
        "performance_pressure": ("売上", "指名", "同伴", "プレッシャー", "負担"),
    },
    "liver_manager": {
        "first_viewer_retention": ("初見", "入室", "挨拶", "入りやす"),
        "comment_activation": ("コメント", "質問", "話題", "会話", "答えやすい", "声かけ"),
        "agency_selection": ("事務所", "所属先", "所属条件", "事務所選び"),
        "creator_support": ("相談", "サポート", "支え", "一緒に", "改善"),
        "continuity": ("配信時間", "継続", "習慣", "リズム", "続け", "休む"),
        "monetization": ("ギフト", "投げ銭", "収益", "ダイヤ"),
        "community_building": ("リスナー", "常連", "応援", "関係", "また来", "枠を支え"),
        "stream_review": ("振り返り", "数字", "改善", "見直"),
        "stream_planning": ("企画", "構成", "終わり方", "配信設計"),
    },
}

TOPIC_COPY: dict[str, dict[str, tuple[str, str]]] = {
    "night_scout": {
        "work_conditions": (
            "夜職で時給や条件を確認するとき、実際の話を店選びの判断材料として整理しておきたい。",
            "店を選ぶ前に、時給と条件をもう一度確認して考える材料にしてください。",
        ),
        "workplace_fit": (
            "夜職の店選びでは、店舗や客層の話を自分との相性を考える材料として整理したい。",
            "お店を選ぶ前に、店舗の雰囲気や客層を確認して考える材料にしてください。",
        ),
        "transfer": (
            "夜職で移籍や次の店を考えるとき、実際の話を判断材料として整理しておきたい。",
            "移籍を決める前に、次の店で続けられるか確認して考える材料にしてください。",
        ),
        "schedule_balance": (
            "夜職の出勤や副業との両立を考えるとき、生活との関係を判断材料として整理したい。",
            "出勤を決める前に、副業や生活と無理なく続けられるか確認してください。",
        ),
        "support_system": (
            "夜職で担当や相談できる環境を選ぶとき、実際の話を判断材料として整理しておきたい。",
            "店を選ぶ前に、担当へ相談できる環境か確認して考える材料にしてください。",
        ),
        "performance_pressure": (
            "夜職で売上や指名の負担を考えるとき、実際の話を店選びの判断材料として整理したい。",
            "店を選ぶ前に、売上や指名を無理なく続けられるか確認してください。",
        ),
    },
    "liver_manager": {
        "first_viewer_retention": (
            "配信で初見が入りやすい状態を作るには、入室直後の動きを具体的に確認する方がいいと思います。",
            "まず初見が入室した場面を見直すだけでも、配信の入りやすさを整えられます。",
        ),
        "comment_activation": (
            "配信でコメントを増やすには、質問や話題の置き方を具体的に確認する方がいいと思います。",
            "まずコメントが生まれる場面を見直すと、次の配信で試す行動を決めやすくなります。",
        ),
        "agency_selection": (
            "ライバーが事務所を選ぶときは、所属条件の話を具体的に確認する方がいいと思います。",
            "まず事務所選びの条件を見直すと、所属先を決める理由を整理できます。",
        ),
        "creator_support": (
            "配信の相談やサポートを考えるときは、実際の支え方を具体的に確認する方がいいと思います。",
            "まず相談できる場面を見直すと、ライバーに必要なサポートを整えやすくなります。",
        ),
        "continuity": (
            "配信を継続するには、配信時間や生活リズムの話を具体的に確認する方がいいと思います。",
            "まず続けられる配信時間を見直すと、無理のない継続方法を決めやすくなります。",
        ),
        "monetization": (
            "配信のギフトや収益を考えるときは、ダイヤにつながる場面を具体的に確認する方がいいと思います。",
            "まずギフトが生まれた場面を見直すと、次の配信で試す行動を決めやすくなります。",
        ),
        "community_building": (
            "配信でリスナーとの関係を作るには、応援が生まれる場面を具体的に確認する方がいいと思います。",
            "まずリスナーが応援しやすい場面を見直すと、配信の関係づくりを整えられます。",
        ),
        "stream_review": (
            "配信を改善するには、振り返りや数字の見方を具体的に確認する方がいいと思います。",
            "まず配信の振り返りを見直すと、次に改善する行動を決めやすくなります。",
        ),
        "stream_planning": (
            "配信の企画や構成を整えるには、実際の進め方を具体的に確認する方がいいと思います。",
            "まず配信構成を見直すと、次の企画で試す行動を決めやすくなります。",
        ),
    },
}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _sentences(value: str) -> list[str]:
    return [
        item.strip(" 　、,。")
        for item in re.split(r"[。！？!?\n]+", _text(value))
        if len(item.strip(" 　、,")) >= 12
    ]


def _clean_claim(value: str, account_id: str) -> str:
    text = re.sub(r"\s+", "", _text(value))
    patterns = (
        (r"(?:私は|私が|わたしは|わたしが|俺は|俺が)", "")
        if account_id == "night_scout"
        else (r"(?:僕は|僕が|ぼくは|ぼくが|俺は|俺が|おれは|おれが)", "")
    )
    text = re.sub(patterns[0], patterns[1], text)
    text = re.sub(r"^(?:えー|えっと|あの|まあ|その)+", "", text)
    text = text.strip(" 　、,。")
    if len(text) > 62:
        text = text[:62].rstrip(" 　、,")
    return text


def _topic_scores(account_id: str, text: str) -> list[tuple[str, int]]:
    scores: list[tuple[str, int]] = []
    for topic, terms in TOPIC_TERMS.get(account_id, {}).items():
        score = sum(text.count(term) * (2 if len(term) >= 4 else 1) for term in terms)
        if score:
            scores.append((topic, score))
    return sorted(scores, key=lambda item: (-item[1], item[0]))


def _claim_candidates(account_id: str, source: str, topic: str) -> list[tuple[str, str]]:
    terms = TOPIC_TERMS[account_id][topic]
    candidates: list[tuple[str, str, int]] = []
    for sentence in _sentences(source):
        positions = [sentence.find(term) for term in terms if term in sentence]
        if not positions:
            continue
        first = min(position for position in positions if position >= 0)
        evidence = sentence
        if len(evidence) > 110:
            start = max(0, first - 28)
            evidence = evidence[start:start + 105].strip(" 　、,")
        topic_score = sum(evidence.count(term) for term in terms)
        claim = _clean_claim(evidence, account_id)
        if len(claim) < 18 or not any(term in claim for term in terms):
            continue
        candidates.append((claim, evidence, topic_score))
    candidates.sort(key=lambda item: (-item[2], abs(len(item[0]) - 42), item[0]))
    return [(claim, evidence) for claim, evidence, _score in candidates[:8]]


def _variants(hook: str, claim: str, closing: str) -> list[str]:
    return [
        f"{hook}\n\nこの場面では「{claim}」と話されています。\n\n{closing}",
        f"{hook}\n\n「{claim}」という話があります。\n\n{closing}",
        f"{hook}\n\n判断するときに確認したいのは「{claim}」という部分です。\n\n{closing}",
        f"{hook}\n\n実際の言葉は「{claim}」。\n\n{closing}",
    ]


def generate_evidence_context_caption(
    *,
    account_id: str,
    transcript_excerpt: str,
    recent_posts: list[str] | None = None,
) -> dict[str, Any]:
    source = _text(transcript_excerpt)
    recent = [str(item) for item in (recent_posts or []) if _text(item)]
    suitability, source_blockers = clip_source_suitability(
        account_id=account_id,
        transcript=source,
    )
    if account_id not in TOPIC_TERMS or source_blockers:
        return {
            "status": "BLOCKED",
            "public_post_text": "",
            "provider_name": PROVIDER_NAME,
            "provider_version": PROVIDER_VERSION,
            "provider_status": "BLOCKED",
            "semantic_alignment": {"status": "BLOCKED", "blocked_reasons": source_blockers},
            "claim_support": [],
            "internal_analysis": {},
            "blocked_reasons": source_blockers or ["unsupported_account"],
        }

    rejections: set[str] = set()
    alignment_provider = LocalSemanticAlignmentProvider()
    ranked_topics = _topic_scores(account_id, source)
    seed = int(hashlib.sha256(source.encode("utf-8")).hexdigest()[:8], 16)

    for topic, _score in ranked_topics:
        hook, closing = TOPIC_COPY[account_id][topic]
        claims = _claim_candidates(account_id, source, topic)
        if not claims:
            rejections.add("topic_claim_missing")
            continue
        for claim_index, (claim, evidence) in enumerate(claims):
            variants = _variants(hook, claim, closing)
            offset = (seed + claim_index) % len(variants)
            for step in range(len(variants)):
                public_text = variants[(offset + step) % len(variants)]
                validation = final_public_post_validator(public_text, account_id)
                if validation.get("status") != "PASS":
                    rejections.update(str(item) for item in validation.get("blocked_reasons", []) if str(item))
                    continue
                support = [{"caption_claim": claim, "source_evidence": evidence}]
                alignment = alignment_provider.evaluate(
                    source_text=source,
                    public_post_text=public_text,
                    main_claims=[claim],
                    claim_support=support,
                    recent_posts=recent,
                    alignment_mode="transform",
                )
                semantic = alignment.data if isinstance(alignment.data, dict) else {}
                if alignment.status != "PASS":
                    rejections.update(str(item) for item in semantic.get("blocked_reasons", []) if str(item))
                    continue
                quality = evaluate_generation_quality(
                    account_id,
                    public_text,
                    recent,
                    batch_compared=[],
                    structure_variant=f"evidence_context_{topic}_{step}",
                    visual_text=source,
                    primary_topic=topic,
                )
                if quality.get("status") != "PASS":
                    rejections.update(str(item) for item in quality.get("diversity_blocked_reasons", []) if str(item))
                    rejections.update(str(item) for item in quality.get("topic_blocked_reasons", []) if str(item))
                    continue
                internal = {
                    "main_claims": [claim],
                    "topic": topic,
                    "core_topic": topic,
                    "main_claim": claim,
                    "hook": hook,
                    "supporting_points": [claim],
                    "concrete_example": claim,
                    "conclusion": closing,
                    "audience": (
                        "夜職を始めたい、店選びや移籍で悩む女性"
                        if account_id == "night_scout"
                        else "配信初心者、伸び悩むライバー、事務所選びで迷う人"
                    ),
                    "intended_audience": (
                        "夜職を始めたい、店選びや移籍で悩む女性"
                        if account_id == "night_scout"
                        else "配信初心者、伸び悩むライバー、事務所選びで迷う人"
                    ),
                    "media_role": "exact_transcript_evidence",
                    "factual_constraints": [evidence],
                    "prohibited_inferences": ["字幕にない数値・経験・結果を追加しない"],
                }
                return {
                    "status": "PASS",
                    "source_mode": "transform",
                    "public_post_text": public_text,
                    "provider_name": PROVIDER_NAME,
                    "provider_version": PROVIDER_VERSION,
                    "provider_status": "PASS",
                    "semantic_alignment": semantic,
                    "claim_support": support,
                    "internal_analysis": internal,
                    "generation_quality": quality,
                    "source_suitability": suitability,
                    "blocked_reasons": [],
                }

    return {
        "status": "BLOCKED",
        "public_post_text": "",
        "provider_name": PROVIDER_NAME,
        "provider_version": PROVIDER_VERSION,
        "provider_status": "BLOCKED",
        "semantic_alignment": {"status": "BLOCKED", "blocked_reasons": sorted(rejections)},
        "claim_support": [],
        "internal_analysis": {},
        "blocked_reasons": sorted(rejections) or ["evidence_context_candidate_exhausted"],
    }
