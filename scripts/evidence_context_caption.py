#!/usr/bin/env python3
"""Deterministic reader-context captions grounded in one exact transcript window."""
from __future__ import annotations

import hashlib
import json
import os
import re
from typing import Any

from acquisition.contracts import ProviderResult
from acquisition.models import SourcePostBundle
from generation.semantic_alignment import LocalSemanticAlignmentProvider
from generation.source_grounded_caption import GitHubModelsGroundedProvider, account_rules
from generation_quality_gates import evaluate_generation_quality
from gemini_hybrid_client import GeminiHybridClient
from media_activation_source_suitability import clip_source_suitability
from public_post_quality import apply_account_voice, final_public_post_validator

PROVIDER_NAME = "deterministic_evidence_context"
PROVIDER_VERSION = "3"

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
    "beauty_account": {
        "skincare_routine": ("スキンケア", "化粧水", "乳液", "保湿", "乾燥", "毛穴", "肌"),
        "base_makeup": ("ファンデ", "下地", "ベースメイク", "コンシーラー", "色ムラ"),
        "haircare_method": ("ヘアケア", "髪", "トリートメント", "オイル", "ドライヤー"),
        "beauty_device_selection": ("美容家電", "アイロン", "ブラシ", "パフ", "スポンジ"),
        "beauty_choice": ("美容", "メイク", "リップ", "チーク", "アイシャドウ", "サロン", "ネイル", "まつげ"),
    },
}

TOPIC_COPY: dict[str, dict[str, tuple[str, str]]] = {
    "night_scout": {
        "work_conditions": (
            "僕が夜職で時給や条件を確認するとき、実際の話を店選びの判断材料として整理しておきたい。",
            "店を選ぶ前に、時給と条件をもう一度確認して考える材料にしてください。",
        ),
        "workplace_fit": (
            "僕が夜職の店選びを考えるとき、店舗や客層の話を自分との相性を考える材料として整理したい。",
            "お店を選ぶ前に、店舗の雰囲気や客層を確認して考える材料にしてください。",
        ),
        "transfer": (
            "僕が夜職で移籍や次の店を考えるとき、実際の話を判断材料として整理しておきたい。",
            "移籍を決める前に、次の店で続けられるか確認して考える材料にしてください。",
        ),
        "schedule_balance": (
            "僕が夜職の出勤や副業との両立を考えるとき、生活との関係を判断材料として整理したい。",
            "出勤を決める前に、副業や生活と無理なく続けられるか確認してください。",
        ),
        "support_system": (
            "僕が夜職で担当や相談できる環境を選ぶとき、実際の話を判断材料として整理しておきたい。",
            "店を選ぶ前に、担当へ相談できる環境か確認して考える材料にしてください。",
        ),
        "performance_pressure": (
            "僕が夜職で売上や指名の負担を考えるとき、実際の話を店選びの判断材料として整理しておきたい。",
            "店を選ぶ前に、売上や指名を無理なく続けられるか確認してください。",
        ),
    },
    "liver_manager": {
        "first_viewer_retention": (
            "初見が入った瞬間って、どう返すか迷うよね。配信の入り口はここが意外と大事なんだよね。",
            "次の配信では、入室した人への反応を一つだけ見直して試してみてね。",
        ),
        "comment_activation": (
            "コメントって、何を聞くかより答えやすい空気があるかで変わることあるよね。配信ではここが大事なんだよね。",
            "次の配信では、質問を一つだけ用意して試してみてね。",
        ),
        "agency_selection": (
            "ライバーが事務所を選ぶときって、条件だけ見てると迷うことあるよね。所属後に続けやすいかも大事なんだよね。",
            "事務所を見るときは、気になる条件を一つだけ確認してみてね。",
        ),
        "creator_support": (
            "ライバーの配信って、一人で全部抱えるとしんどいことあるよね。相談できる環境があるかは意外と大事なんだよね。",
            "次の配信では、困っていることを一つだけ整理して相談してみてね。",
        ),
        "continuity": (
            "ライバーが配信を続けるなら、無理な時間に合わせ続ける方がしんどいことあるよね。",
            "次の配信では、続けやすい配信時間を一つだけ見直してみてね。",
        ),
        "monetization": (
            "配信でギフトを増やしたいときって、いきなり全部変えようとすると迷うよね。",
            "次の配信では、ギフトが生まれた場面を一つだけ見直して試してみてね。",
        ),
        "community_building": (
            "リスナーとのやり取りって、小さい反応でも配信の空気が変わることあるよね。",
            "次の配信では、リスナーへの声かけを一つだけ試してみてね。",
        ),
        "stream_review": (
            "ライバーが配信を振り返るとき、全部直そうとすると逆に迷うことあるよね。",
            "次の配信では、変えるところを一つだけ決めて試してみてね。",
        ),
        "stream_planning": (
            "ライバーの配信企画って、やることを増やしすぎると逆に伝わりにくくなることあるよね。",
            "次の配信では、企画で試すことを一つだけ決めてみてね。",
        ),
    },
    "beauty_account": {
        "skincare_routine": (
            "スキンケアって、一度に全部変えるより一つずつ見直す方が肌の反応を見やすいんだけど、これ結構大事。",
            "個人的には、まず一つだけ試して肌の変化を見てみてほしい。",
        ),
        "base_makeup": (
            "ベースメイクって、重ねる量よりどこを整えるかで仕上がりが変わる気がする。",
            "気になる部分を一つ決めて、薄く重ねながら見てみてほしい。",
        ),
        "haircare_method": (
            "ヘアケアって、アイテムを増やす前に使う量と順番を見直すのが意外と大事。",
            "今のケアを一つだけ変えて、髪のまとまりを比べてみてほしい。",
        ),
        "beauty_device_selection": (
            "美容家電やツールは、機能の多さより自分が続けて使えるかで選ぶのがいい気がする。",
            "毎日使う場面を一つ想像して、操作やお手入れまで見てみてほしい。",
        ),
        "beauty_choice": (
            "メイクやサロン選びって、流行を全部足すより今の自分に合うポイントを一つ拾う方がほんとに使いやすい。",
            "気になるポイントを一つ決めて、普段のケアと比べてみてほしい。",
        ),
    },
}

AUDIENCES = {
    "night_scout": "夜職を始めたい、店選びや移籍で悩む女性",
    "liver_manager": "配信初心者、伸び悩むライバー、事務所選びで迷う人",
    "beauty_account": "20〜30代の美容・コスメ好きの女性",
}


class PrivacyBoundedGeminiGroundedProvider:
    """Generate direct-media captions without sending transcripts or history."""

    provider_name = "gemini_direct_caption"
    provider_version = "privacy_bounded_v1"

    def __init__(self, client: GeminiHybridClient | None = None) -> None:
        self.client = client or GeminiHybridClient()

    @property
    def available(self) -> bool:
        return bool(self.client.api_key)

    def generate(
        self,
        post: SourcePostBundle,
        *,
        account_id: str,
        recent_posts: list[str],
        transcript_excerpt: str = "",
        source_mode: str = "transform",
    ) -> ProviderResult[dict[str, Any]]:
        del recent_posts, transcript_excerpt
        if not self.available:
            return ProviderResult(
                self.provider_name,
                self.provider_version,
                "UNAVAILABLE",
                reason="gemini_api_key_missing",
            )
        schema = {
            "type": "object",
            "properties": {
                "internal_analysis": {"type": "object"},
                "public_post_text": {"type": "string", "minLength": 1},
                "claim_support": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "caption_claim": {"type": "string"},
                            "source_evidence": {"type": "string"},
                        },
                        "required": ["caption_claim", "source_evidence"],
                    },
                },
                "safety_notes": {"type": "string"},
                "blocked_reasons": {"type": "array", "items": {"type": "string"}},
            },
            "required": [
                "internal_analysis",
                "public_post_text",
                "claim_support",
                "safety_notes",
                "blocked_reasons",
            ],
        }
        safe_input = {
            "target_account_id": account_id,
            "account_rules": account_rules(account_id),
            "caption_mode": source_mode,
            "source_url": post.canonical_post_url,
            "source_post_text": post.original_post_text[:6000],
            "media_metadata": [
                {
                    "media_type": item.media_type,
                    "duration_seconds": item.duration_seconds,
                    "width": item.width,
                    "height": item.height,
                }
                for item in post.media_items
            ],
        }
        prompt = (
            "日本語Threadsの公開本文をJSONで作成する。"
            "source、reference、metadata、transcript、AIなどの内部語を公開文に出さない。"
            "参照投稿だけを根拠に、80〜500文字、1投稿1テーマの新しい読者向け本文にする。"
            "数値・事実・経験を捏造せず、元投稿者の所属や実績を対象アカウント自身の実績に見せない。"
            "public_post_textの実質的主張ごとにclaim_supportを作り、source_evidenceは入力文の短い正確な根拠にする。"
            "internal_analysisにmain_claims、core_topic、intended_audience、factual_constraints、prohibited_inferencesを入れる。\n"
            + json.dumps(safe_input, ensure_ascii=False)
        )
        try:
            result = self.client.generate_json(
                model=os.environ.get("GEMINI_GENERATOR_MODEL", "gemini-3.5-flash"),
                prompt=prompt,
                schema=schema,
                operation="direct_reference_caption_generation",
                account_id=account_id,
                cache_context={
                    "source_post_id": post.source_post_id,
                    "content_hash": post.content_hash,
                    "caption_mode": source_mode,
                },
            )
        except RuntimeError as exc:
            return ProviderResult(
                self.provider_name,
                self.provider_version,
                "FAILED",
                reason=f"{type(exc).__name__}:gemini_direct_caption_failed",
                retryable=True,
            )
        return ProviderResult(
            self.provider_name,
            self.provider_version,
            "PASS",
            data=dict(result["data"]),
            metadata={"model": str(result.get("model", "")), "privacy_scope": "source_text_only"},
        )


class DirectCaptionProviderFailover:
    """GitHub Models first, then privacy-bounded Gemini for direct media."""

    provider_name = "direct_caption_provider_failover"
    provider_version = "1"

    def __init__(
        self,
        primary: Any | None = None,
        fallback: Any | None = None,
    ) -> None:
        self.primary = primary or GitHubModelsGroundedProvider()
        self.fallback = fallback or PrivacyBoundedGeminiGroundedProvider()

    def generate(self, post: SourcePostBundle, **kwargs: Any) -> ProviderResult[dict[str, Any]]:
        primary = self.primary.generate(post, **kwargs)
        if primary.ok or not getattr(self.fallback, "available", False):
            return primary
        fallback = self.fallback.generate(post, **kwargs)
        if fallback.ok:
            return fallback
        return ProviderResult(
            self.provider_name,
            self.provider_version,
            "FAILED",
            reason="|".join(filter(None, (primary.reason, fallback.reason))),
            retryable=primary.retryable or fallback.retryable,
            metadata={"primary_provider": self.primary.provider_name, "fallback_provider": self.fallback.provider_name},
        )


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
    return text


def transcript_claim_quality_blockers(value: str) -> list[str]:
    """Reject visibly corrupted or arbitrarily incomplete transcript claims."""

    text = _text(value)
    reasons: list[str] = []
    if len(text) > 72:
        reasons.append("transcript_claim_too_long_for_standalone_quote")
    if re.search(r"[A-Z]{6,}|[=<>|{}]|ですねね|だぁだ|てで=", text):
        reasons.append("transcript_claim_corrupted")
    latin_count = len(re.findall(r"[A-Za-z]", text))
    if text and latin_count / len(text) > 0.12:
        reasons.append("transcript_claim_latin_noise")
    if text.endswith(("ってい", "とい", "でし", "まし")):
        reasons.append("transcript_claim_truncated")
    return sorted(set(reasons))


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
        if (
            len(claim) < 18
            or transcript_claim_quality_blockers(claim)
            or not any(term in claim for term in terms)
        ):
            continue
        candidates.append((claim, evidence, topic_score))
    candidates.sort(key=lambda item: (-item[2], abs(len(item[0]) - 42), item[0]))
    return [(claim, evidence) for claim, evidence, _score in candidates[:8]]


def _variants(
    hook: str,
    claim: str,
    closing: str,
) -> list[str]:
    """Try conversational evidence-first variants before formal fallbacks."""
    return [
        f"{hook}\n\n「{claim}」と話しています。\n\n{closing}",
        f"{hook}\n\n{claim}。\n\n{closing}",
        f"{hook}\n\nこの場面では「{claim}」と話されています。\n\n{closing}",
        f"{hook}\n\n「{claim}」という話があります。\n\n{closing}",
        f"{hook}\n\n判断するときに確認したいのは「{claim}」という部分です。\n\n{closing}",
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
                public_text = apply_account_voice(
                    variants[(offset + step) % len(variants)],
                    account_id,
                )
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
                    "audience": AUDIENCES[account_id],
                    "intended_audience": AUDIENCES[account_id],
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
