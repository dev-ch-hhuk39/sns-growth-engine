"""Source-specific caption generation backed by GitHub Models.

The provider produces structured private analysis and a separate public field.
Only ``public_post_text`` may cross the publishing boundary.  Every result is
then checked against source evidence and recent posts before it is eligible.
"""
from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests

from acquisition.contracts import ProviderResult
from acquisition.models import SourcePostBundle
from generation.semantic_alignment import (
    ALIGNMENT_THRESHOLDS,
    LocalSemanticAlignmentProvider,
    lexical_similarity,
)
from generation.source_copyedit import (
    DeterministicSourceCopyeditProvider,
    evaluate_source_copyedit_contract,
)

try:
    from accounts.managed_accounts import managed_account
except ModuleNotFoundError:  # package imported as src.generation.* in legacy tests
    from src.accounts.managed_accounts import managed_account

ROOT = Path(__file__).resolve().parents[2]

ACCOUNT_RULES = {
    "night_scout": {
        "audience": "夜職を始めたい、店選びや移籍で悩む女性",
        "purpose": "不安を言語化し、続けられる店や働き方の判断材料を渡す",
        "cta": "必要な場合だけ、相談余地を最後に一言添える",
        "banned": "誇大な収入断定、強い求人、説教、店舗名の羅列",
        "voice": "原文の意味と順番を維持し、なんよな・かな・僕なら等は必要な箇所だけ使う",
    },
    "liver_manager": {
        "audience": "配信初心者、伸び悩むライバー、事務所選びで迷う人",
        "purpose": "配信のつまずきを具体化し、今日変えられる行動を示す",
        "cta": "必要な場合だけ、相談余地を最後に一言添える",
        "banned": "楽して稼げる断定、ギフト要求、他社批判、精神論だけの助言",
        "voice": "原文の意味と面白さを維持し、標準的な話し言葉と現場視点を自然に使う",
    },
}


def _account_config(account_id: str) -> dict[str, Any]:
    record = managed_account(account_id)
    path = ROOT / str(record["account_config"])
    return json.loads(path.read_text(encoding="utf-8"))


def account_rules(account_id: str) -> dict[str, str]:
    """Build source-caption rules from the canonical account configuration."""
    cfg = _account_config(account_id)
    legacy = ACCOUNT_RULES.get(account_id, {})
    cta_policy = cfg.get("cta_policy", {})
    forbidden = list(cfg.get("forbidden_themes", [])) + list(cfg.get("forbidden_keywords", []))
    return {
        "audience": str(cfg.get("target_audience") or legacy.get("audience") or "account-specific audience"),
        "purpose": str(cfg.get("primary_goal") or legacy.get("purpose") or "give one useful reader-facing action"),
        "cta": str(cta_policy.get("style") or cta_policy.get("default") or legacy.get("cta") or "CTA is optional and must be light"),
        "banned": ", ".join(str(value) for value in forbidden[:40]) or str(legacy.get("banned") or "fabricated claims and internal processing terms"),
        "voice": str(cfg.get("tone") or legacy.get("voice") or cfg.get("persona") or "natural account-specific spoken Japanese"),
    }


def account_evidence_terms(account_id: str) -> tuple[str, ...]:
    """Return bounded, account-owned evidence vocabulary for deterministic grounding."""
    cfg = _account_config(account_id)
    generation = cfg.get("generation", {})
    configured = [
        str(term)
        for terms in generation.get("topic_keywords", {}).values()
        for term in (terms if isinstance(terms, list) else [])
        if str(term).strip()
    ]
    legacy = list(DeterministicGroundedProvider.EVIDENCE_TERMS.get(account_id, ()))
    return tuple(dict.fromkeys(legacy + configured))


def _json_object(text: str) -> dict[str, Any]:
    cleaned = str(text or "").strip()
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", cleaned, flags=re.IGNORECASE)
    value = json.loads(cleaned)
    if not isinstance(value, dict):
        raise ValueError("model_response_must_be_object")
    return value


class GitHubModelsGroundedProvider:
    provider_name = "github_models"
    provider_version = "2026-03-10"

    def __init__(self, *, token: str | None = None, model: str | None = None, timeout_seconds: int = 60):
        self._token = token or os.environ.get("GITHUB_TOKEN", "")
        self.model = model or os.environ.get("GITHUB_MODELS_MODEL", "openai/gpt-4.1")
        self.timeout_seconds = min(max(timeout_seconds, 10), 90)
        self.endpoint = os.environ.get("GITHUB_MODELS_ENDPOINT", "https://models.github.ai/inference/chat/completions")

    @property
    def available(self) -> bool:
        return bool(self._token) and os.environ.get("GITHUB_MODELS_ENABLED", "").lower() in {"1", "true", "yes"}

    def generate(
        self,
        post: SourcePostBundle,
        *,
        account_id: str,
        recent_posts: list[str],
        transcript_excerpt: str = "",
        source_mode: str = "transform",
    ) -> ProviderResult[dict[str, Any]]:
        if not self.available:
            return ProviderResult(self.provider_name, self.provider_version, "UNAVAILABLE", reason="github_models_not_enabled_or_token_missing")
        rules = account_rules(account_id)
        comments = [
            {"text": str(row.get("text", ""))[:300], "like_count": row.get("like_count", "")}
            for row in post.comments[:20]
        ]
        source_payload = {
            "source_post_id": post.source_post_id,
            "original_post_text": post.original_post_text[:6000],
            "transcript_excerpt": transcript_excerpt[:6000],
            "comments": comments,
            "media": [
                {"media_type": item.media_type, "duration_seconds": item.duration_seconds, "width": item.width, "height": item.height}
                for item in post.media_items
            ],
        }
        if source_mode == "source_copyedit":
            developer_prompt = (
                "あなたはSNSの校正編集者です。出力はJSONオブジェクトのみ。"
                "original_post_textを別テーマの記事へ作り替えず、意味、主張、固有名詞、"
                "数値、話の順番、ユーモアを維持したまま校正する。"
                "変更できるのは誤字、句読点、改行、一人称、不要なURL、"
                "メンション、ハッシュタグ、軽い口調調整だけ。"
                "元文にない判断基準、助言、数字、体験、結論を追加しない。"
                "元投稿者の経験、担当数、実績、所属、商品使用などの事実は、"
                "対象アカウント本人の事実に書き換えない。"
                "その情報を公開文に残す場合は、この動画では、投稿者は、"
                "と話している、等で元投稿者への帰属を明示する。"
                "transcript_excerptは同じ親投稿のメディア確認用であり、"
                "original_post_textより優先しない。"
                "夜職スカウトでは、なんよな・かな・僕なら等を必要な箇所だけ使い、"
                "毎文繰り返さない。"
                "ライバーマネージャーでは、標準的な話し言葉を使い、"
                "元投稿にない教育論や改善策を追加しない。"
                "確認することは一つ、この順番で考える理由はシンプル、"
                "見るポイントは次の通り、次に試すこと、という固定文を使わない。"
                "元投稿名、URL、source、reference、metadata、transcript、AI、"
                "内部処理語を公開文に書かない。"
                "public_post_textの主張をclaim_supportへ列挙し、"
                "source_evidenceはoriginal_post_textから正確に引用する。"
                "internal_analysisにはcore_topic, main_claim, hook, supporting_points, "
                "concrete_example, conclusion, intended_audience, media_role, "
                "factual_constraints, prohibited_inferences, main_claimsを含める。"
                "JSON keys: internal_analysis, public_post_text, "
                "claim_support[{caption_claim,source_evidence}], safety_notes, blocked_reasons。"
            )
        else:
            developer_prompt = (
                "あなたはSNS編集者です。入力された1件の参照投稿だけを根拠に、日本語Threads本文を作成してください。"
                "出力はJSONオブジェクトのみ。元投稿名、URL、source、reference、metadata、transcript、AI、内部処理語を公開文に書かない。"
                "数値・事実・経験を捏造しない。元文の長いコピーを避け、1投稿1テーマ、80〜500文字の自然な読者向け文章にする。"
                "public_post_textの各実質的主張をclaim_supportへ列挙し、source_evidenceは入力中の根拠文を短く正確に引用する。"
                "internal_analysisにはcore_topic, main_claim, hook, supporting_points, concrete_example, conclusion, "
                "intended_audience, media_role, factual_constraints, prohibited_inferences, main_claimsを必ず含める。"
                "JSON keys: internal_analysis, public_post_text, claim_support[{caption_claim,source_evidence}], safety_notes, blocked_reasons。"
            )
        user_prompt = json.dumps({
            "account_rules": rules,
            "caption_mode": source_mode,
            "source_bundle": source_payload,
            "recent_public_posts_for_dedupe": [text[:600] for text in recent_posts[-20:]],
        }, ensure_ascii=False)
        payload = {
            "model": self.model,
            "temperature": 0.2,
            "max_tokens": 1200,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "developer", "content": developer_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        started = time.monotonic()
        try:
            response = requests.post(
                self.endpoint,
                headers={
                    "Accept": "application/vnd.github+json",
                    "Authorization": f"Bearer {self._token}",
                    "X-GitHub-Api-Version": self.provider_version,
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
            body = response.json()
            content = body["choices"][0]["message"]["content"]
            data = _json_object(content)
            return ProviderResult(
                self.provider_name,
                self.provider_version,
                "PASS",
                data=data,
                duration_ms=int((time.monotonic() - started) * 1000),
                metadata={"model": self.model},
            )
        except (requests.RequestException, KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError) as exc:
            # Never include response bodies or authorization material.
            return ProviderResult(
                self.provider_name,
                self.provider_version,
                "FAILED",
                reason=f"{type(exc).__name__}:github_models_generation_failed",
                retryable=True,
                duration_ms=int((time.monotonic() - started) * 1000),
                metadata={"model": self.model},
            )


class DeterministicGroundedProvider:
    """Bounded source-derived fallback for transient model unavailability.

    It searches a finite set of deterministic compositions and accepts only a
    candidate that passes the same semantic-alignment and recent-post dedupe
    gate used by the outer service. Thresholds are never relaxed.
    """

    provider_name = "deterministic_grounded_fallback"
    provider_version = "4"

    MAX_GENERATION_ATTEMPTS = 64
    MAX_DISTINCT_CANDIDATES = 18

    EVIDENCE_TERMS = {
        "night_scout": (
            "夜職",
            "店",
            "店舗",
            "時給",
            "ノルマ",
            "客層",
            "出勤",
            "移籍",
            "副業",
            "相談",
            "風俗",
            "風俗嬢",
            "キャバ",
            "キャバ嬢",
            "ラウンジ",
            "ホスト",
            "スカウト",
            "ナイトワーク",
        ),
        "liver_manager": (
            "配信",
            "配信者",
            "初見",
            "コメント",
            "リスナー",
            "ギフト",
            "事務所",
            "継続",
            "話題",
            "ライバー",
            "ライブ",
            "TikTok LIVE",
            "tiktoklive",
            "バトル",
            "配信枠",
            "団結",
            "コイン",
            "投げる",
            "投げ",
        ),
    }

    @staticmethod
    def _sentences(
        text: str,
    ) -> list[str]:
        return [
            item.strip()
            for item in re.split(
                r"[。！？!?\n]+",
                str(text or ""),
            )
            if item.strip()
        ]

    def generate(
        self,
        post: SourcePostBundle,
        *,
        account_id: str,
        recent_posts: list[str],
        transcript_excerpt: str = "",
    ) -> ProviderResult[dict[str, Any]]:
        signal = "\n".join(
            filter(
                None,
                [
                    transcript_excerpt,
                    post.original_post_text,
                ],
            )
        ).strip()

        terms = account_evidence_terms(account_id)

        evidence_candidates = [
            sentence
            for sentence in self._sentences(signal)
            if any(
                term.casefold() in sentence.casefold()
                for term in terms
            )
        ]

        if not evidence_candidates:
            return ProviderResult(
                self.provider_name,
                self.provider_version,
                "UNAVAILABLE",
                reason=(
                    "account_relevant_source_evidence_missing"
                ),
            )

        evidence = max(
            evidence_candidates,
            key=lambda sentence: (
                sum(
                    term.casefold() in sentence.casefold()
                    for term in terms
                ),
                len(sentence),
            ),
        )[:300]

        try:
            from public_post_quality import (
                generate_grounded_reader_facing_post,
            )
        except ImportError:
            return ProviderResult(
                self.provider_name,
                self.provider_version,
                "UNAVAILABLE",
                reason=(
                    "public_post_generator_unavailable"
                ),
            )

        content_hash = str(
            getattr(
                post,
                "content_hash",
                "",
            )
            or ""
        )

        base_index = (
            max(
                1,
                int(
                    content_hash[:8],
                    16,
                ),
            )
            if content_hash
            else 1
        )

        alignment_provider = (
            LocalSemanticAlignmentProvider()
        )

        seen_texts: set[str] = set()
        evaluated_count = 0
        rejection_reasons: set[str] = set()

        for attempt in range(
            self.MAX_GENERATION_ATTEMPTS
        ):
            composition_index = (
                base_index
                + attempt * 104729
            )

            structure_variant = (
                base_index
                + attempt
            ) % 6

            generated = (
                generate_grounded_reader_facing_post(
                    account_id,
                    private_signal=signal,
                    index=composition_index,
                    media_metadata={
                        "media_type": post.media_type,
                    },
                    recent_posts=recent_posts,
                    structure_variant=(
                        structure_variant
                    ),
                )
            )

            public_text = str(
                generated.get(
                    "public_post_text",
                    "",
                )
            ).strip()

            if not public_text:
                rejection_reasons.add(
                    "deterministic_caption_empty"
                )
                continue

            if public_text in seen_texts:
                continue

            if (
                evaluated_count
                >= self.MAX_DISTINCT_CANDIDATES
            ):
                break

            seen_texts.add(public_text)
            evaluated_count += 1

            public_sentences = self._sentences(
                public_text
            )

            if not public_sentences:
                rejection_reasons.add(
                    "deterministic_caption_empty"
                )
                continue

            # Every substantive public sentence is a claim.
            # A single weakly related sentence must never be used
            # to validate an otherwise unrelated template.
            caption_claims = [
                sentence
                for sentence in public_sentences
                if len(sentence.strip()) >= 8
            ]

            if not caption_claims:
                rejection_reasons.add(
                    "deterministic_caption_has_no_claims"
                )
                continue

            # Match each public claim to the most relevant
            # exact sentence from the source packet. Comparing
            # every claim with one shared sentence creates both
            # false positives and false negatives.
            claim_support = []

            for caption_claim in caption_claims:
                best_evidence = max(
                    evidence_candidates,
                    key=lambda candidate: (
                        lexical_similarity(
                            caption_claim,
                            candidate,
                        )
                    ),
                )

                claim_support.append({
                    "caption_claim": caption_claim,
                    "source_evidence": best_evidence,
                })

            if any(
                lexical_similarity(
                    item["caption_claim"],
                    item["source_evidence"],
                )
                < ALIGNMENT_THRESHOLDS[
                    "claim_evidence_similarity"
                ]
                for item in claim_support
            ):
                rejection_reasons.add(
                    "deterministic_claim_not_grounded"
                )
                continue

            alignment = (
                alignment_provider.evaluate(
                    source_text=signal,
                    public_post_text=public_text,
                    main_claims=caption_claims,
                    claim_support=claim_support,
                    recent_posts=recent_posts,
                )
            )

            alignment_data = (
                alignment.data
                if isinstance(
                    alignment.data,
                    dict,
                )
                else {}
            )

            generated_blocked = [
                str(reason)
                for reason in generated.get(
                    "blocked_reasons",
                    [],
                )
                if str(reason)
            ]

            alignment_blocked = [
                str(reason)
                for reason in alignment_data.get(
                    "blocked_reasons",
                    [],
                )
                if str(reason)
            ]

            candidate_blocked = sorted(
                set(
                    generated_blocked
                    + alignment_blocked
                )
            )

            if (
                alignment.status == "PASS"
                and not candidate_blocked
            ):
                grounding_summary = (
                    generated.get(
                        "grounding_summary",
                        {},
                    )
                )

                topic = (
                    str(
                        grounding_summary.get(
                            "topic",
                            "",
                        )
                    )
                    if isinstance(
                        grounding_summary,
                        dict,
                    )
                    else ""
                )

                return ProviderResult(
                    self.provider_name,
                    self.provider_version,
                    "PASS",
                    data={
                        "internal_analysis": {
                            "main_claims": (
                                caption_claims
                            ),
                            "topic": topic,
                            "audience": (
                                account_rules(account_id)["audience"]
                            ),
                            "fallback_candidate_count": (
                                evaluated_count
                            ),
                            "fallback_structure_variant": (
                                structure_variant
                            ),
                        },
                        "public_post_text": (
                            public_text
                        ),
                        "claim_support": (
                            claim_support
                        ),
                        "safety_notes": (
                            "Deterministic "
                            "source-grounded fallback; "
                            "raw source stays private."
                        ),
                        "blocked_reasons": [],
                    },
                    metadata={
                        "generation_attempt_count": (
                            attempt + 1
                        ),
                        "distinct_candidate_count": (
                            evaluated_count
                        ),
                    },
                )

            rejection_reasons.update(
                candidate_blocked
                or [
                    alignment.reason
                    or "semantic_alignment_not_passed"
                ]
            )

        return ProviderResult(
            self.provider_name,
            self.provider_version,
            "BLOCKED",
            reason=(
                "deterministic_distinct_"
                "candidate_exhausted"
            ),
            metadata={
                "generation_attempt_count": (
                    self.MAX_GENERATION_ATTEMPTS
                ),
                "distinct_candidate_count": (
                    evaluated_count
                ),
                "rejection_reason_count": len(
                    rejection_reasons
                ),
            },
        )


@dataclass
class SourceGroundedCaptionService:
    generation_provider: Any
    alignment_provider: Any = None
    fallback_provider: Any = None
    copyedit_fallback_provider: Any = None
    allow_deterministic_fallback: bool = False
    retry_primary_on_alignment_failure: bool = True

    def __post_init__(self) -> None:
        if self.alignment_provider is None:
            self.alignment_provider = (
                LocalSemanticAlignmentProvider()
            )

        if (
            self.fallback_provider is None
            and self.allow_deterministic_fallback
        ):
            self.fallback_provider = (
                DeterministicGroundedProvider()
            )

        if (
            self.copyedit_fallback_provider is None
            and self.allow_deterministic_fallback
        ):
            self.copyedit_fallback_provider = (
                DeterministicSourceCopyeditProvider()
            )

    def generate(
        self,
        post: SourcePostBundle,
        *,
        account_id: str,
        recent_posts: list[str] | None = None,
        transcript_excerpt: str = "",
        source_mode: str = "transform",
    ) -> dict[str, Any]:
        if source_mode not in {
            "transform",
            "source_copyedit",
        }:
            return {
                "status": "BLOCKED",
                "source_mode": source_mode,
                "public_post_text": "",
                "internal_analysis": {},
                "safety_notes": "",
                "blocked_reasons": [
                    "unsupported_source_mode"
                ],
                "provider_status": "BLOCKED",
                "primary_provider_failure": "",
            }

        recent_posts = list(
            recent_posts
            or []
        )

        selected_fallback = (
            self.copyedit_fallback_provider
            if source_mode == "source_copyedit"
            else self.fallback_provider
        )

        def invoke_provider(
            provider: Any,
        ) -> ProviderResult[dict[str, Any]]:
            try:
                return provider.generate(
                    post,
                    account_id=account_id,
                    recent_posts=recent_posts,
                    transcript_excerpt=(
                        transcript_excerpt
                    ),
                    source_mode=source_mode,
                )
            except TypeError as exc:
                if "source_mode" not in str(exc):
                    raise

                return provider.generate(
                    post,
                    account_id=account_id,
                    recent_posts=recent_posts,
                    transcript_excerpt=(
                        transcript_excerpt
                    ),
                )

        generated = invoke_provider(
            self.generation_provider
        )

        primary_failure = (
            generated.reason
            if not generated.ok
            else ""
        )

        # Preserve a failed fallback's exact reason for auditing. Previously,
        # when both providers were unavailable, only the primary-provider
        # reason survived and clip-level grounding failures were hidden.
        fallback_failure = ""

        if (
            (
                not generated.ok
                or not generated.data
            )
            and selected_fallback is not None
        ):
            fallback = invoke_provider(
                selected_fallback
            )

            if (
                fallback.ok
                and fallback.data
            ):
                generated = fallback
            else:
                fallback_failure = (
                    fallback.reason
                    or "caption_fallback_unavailable"
                )

        if (
            not generated.ok
            or not generated.data
        ):
            return {
                "status": "BLOCKED",
                "source_mode": source_mode,
                "public_post_text": "",
                "internal_analysis": {},
                "safety_notes": "",
                "blocked_reasons": list(
                    dict.fromkeys(
                        reason
                        for reason in (
                            generated.reason
                            or "caption_provider_unavailable",
                            fallback_failure,
                        )
                        if reason
                    )
                ),
                "provider_status": (
                    generated.status
                ),
                "primary_provider_failure": (
                    primary_failure
                ),
            }

        def evaluate_payload(
            payload: dict[str, Any],
        ):
            internal = (
                dict(
                    payload.get(
                        "internal_analysis",
                        {},
                    )
                )
                if isinstance(
                    payload.get(
                        "internal_analysis"
                    ),
                    dict,
                )
                else {}
            )

            public_text = str(
                payload.get(
                    "public_post_text",
                    "",
                )
            ).strip()

            contract: dict[str, Any] = {}

            if source_mode == "source_copyedit":
                contract = (
                    evaluate_source_copyedit_contract(
                        source_text=(
                            post.original_post_text
                        ),
                        public_post_text=(
                            public_text
                        ),
                        account_id=account_id,
                        recent_posts=(
                            recent_posts
                        ),
                    )
                )

                source_text = str(
                    contract.get(
                        "source_text",
                        "",
                    )
                )

                internal["main_claims"] = [
                    source_text
                ]

                internal["topic"] = (
                    "source_copyedit"
                )

                internal[
                    "copyedit_strategy"
                ] = (
                    "preserve_source_then_polish"
                )

                main_claims = [
                    source_text
                ]

                support = [
                    {
                        "caption_claim": (
                            public_text
                        ),
                        "source_evidence": (
                            source_text
                        ),
                    }
                ]

            else:
                source_text = "\n".join(
                    filter(
                        None,
                        [
                            post.original_post_text,
                            transcript_excerpt,
                        ],
                    )
                )

                main_claims = [
                    str(item).strip()
                    for item in internal.get(
                        "main_claims",
                        [],
                    )
                    if str(item).strip()
                ]

                support = [
                    item
                    for item in payload.get(
                        "claim_support",
                        [],
                    )
                    if isinstance(
                        item,
                        dict,
                    )
                ]

            try:
                alignment = (
                    self.alignment_provider
                    .evaluate(
                        source_text=source_text,
                        public_post_text=(
                            public_text
                        ),
                        main_claims=main_claims,
                        claim_support=support,
                        recent_posts=recent_posts,
                        alignment_mode=(
                            source_mode
                        ),
                    )
                )
            except TypeError as exc:
                if "alignment_mode" not in str(exc):
                    raise

                alignment = (
                    self.alignment_provider
                    .evaluate(
                        source_text=source_text,
                        public_post_text=(
                            public_text
                        ),
                        main_claims=main_claims,
                        claim_support=support,
                        recent_posts=recent_posts,
                    )
                )

            alignment_data = (
                alignment.data
                or {
                    "status": "BLOCKED",
                    "blocked_reasons": [
                        alignment.reason
                        or "semantic_alignment_failed"
                    ],
                }
            )

            blocked = [
                str(item)
                for item in payload.get(
                    "blocked_reasons",
                    [],
                )
                if str(item)
            ]

            blocked.extend(
                alignment_data.get(
                    "blocked_reasons",
                    [],
                )
            )

            blocked.extend(
                contract.get(
                    "blocked_reasons",
                    [],
                )
            )

            return (
                internal,
                support,
                public_text,
                alignment,
                alignment_data,
                sorted(set(blocked)),
                contract,
            )

        data = generated.data

        (
            internal,
            support,
            public_text,
            alignment,
            alignment_data,
            blocked,
            contract,
        ) = evaluate_payload(data)

        primary_attempt_count = 1

        if (
            self.retry_primary_on_alignment_failure
            and (
                blocked
                or alignment.status != "PASS"
            )
        ):
            primary_retry = invoke_provider(
                self.generation_provider
            )

            primary_attempt_count = 2

            if (
                primary_retry.ok
                and primary_retry.data
            ):
                generated = primary_retry
                data = primary_retry.data

                (
                    internal,
                    support,
                    public_text,
                    alignment,
                    alignment_data,
                    blocked,
                    contract,
                ) = evaluate_payload(data)

        if (
            (
                blocked
                or alignment.status != "PASS"
            )
            and selected_fallback is not None
        ):
            fallback = invoke_provider(
                selected_fallback
            )

            if (
                fallback.ok
                and fallback.data
            ):
                generated = fallback
                data = fallback.data

                (
                    internal,
                    support,
                    public_text,
                    alignment,
                    alignment_data,
                    blocked,
                    contract,
                ) = evaluate_payload(data)

        return {
            "status": (
                "PASS"
                if (
                    not blocked
                    and alignment.status == "PASS"
                )
                else "BLOCKED"
            ),
            "source_mode": source_mode,
            "source_copyedit_contract": (
                contract
            ),
            "internal_analysis": internal,
            "public_post_text": (
                public_text
            ),
            "claim_support": support,
            "safety_notes": str(
                data.get(
                    "safety_notes",
                    "",
                )
            ),
            "blocked_reasons": sorted(
                set(blocked)
            ),
            "semantic_alignment": (
                alignment_data
            ),
            "provider_name": (
                generated.provider_name
            ),
            "provider_version": (
                generated.provider_version
            ),
            "provider_status": (
                generated.status
            ),
            "primary_provider_failure": (
                primary_failure
            ),
            "primary_attempt_count": (
                primary_attempt_count
            ),
        }



def build_source_post_bundle(row: dict[str, Any], media_rows: list[dict[str, Any]] | None = None) -> SourcePostBundle:
    from acquisition.models import SourceMediaItem

    media = []
    for index, item in enumerate(media_rows or []):
        media.append(SourceMediaItem(
            source_post_media_id=str(item.get("source_post_media_id") or f"spm_{row.get('source_post_id')}_{index}"),
            source_post_id=str(row.get("source_post_id", "")),
            media_index=int(item.get("media_index") or index),
            media_type=str(item.get("media_type", "")),
            canonical_post_url=str(row.get("canonical_post_url", "")),
            original_media_url=str(item.get("original_media_url", "")),
            resolver_backend=str(item.get("resolver_backend", "sheets")),
            duration_seconds=str(item.get("duration_seconds", "")),
            width=str(item.get("width", "")),
            height=str(item.get("height", "")),
        ))
    comments_raw = row.get("comments_json") or "[]"
    try:
        comments = json.loads(comments_raw) if isinstance(comments_raw, str) else comments_raw
    except json.JSONDecodeError:
        comments = []
    return SourcePostBundle(
        source_post_id=str(row.get("source_post_id", "")),
        source_id=str(row.get("source_id", "")),
        target_account_id=str(row.get("target_account_id", "")),
        platform=str(row.get("platform", "")),
        profile_url=str(row.get("profile_url", "")),
        canonical_post_url=str(row.get("canonical_post_url", "")),
        external_post_id=str(row.get("external_post_id", "")),
        original_post_text=str(row.get("original_post_text", "")),
        published_at=str(row.get("published_at", "")),
        author_name=str(row.get("author_name", "")),
        author_handle=str(row.get("author_handle", "")),
        media_items=tuple(media),
        comments=tuple(comments if isinstance(comments, list) else []),
        detail_status=str(row.get("detail_status", "PARTIAL")),
        collection_backend=str(row.get("collection_backend", "")),
        backend_version=str(row.get("backend_version", "")),
        content_hash=str(row.get("content_hash", "")),
    )
