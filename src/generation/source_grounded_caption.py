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
from typing import Any

import requests

from acquisition.contracts import ProviderResult
from acquisition.models import SourcePostBundle
from generation.semantic_alignment import LocalSemanticAlignmentProvider, lexical_similarity

ACCOUNT_RULES = {
    "night_scout": {
        "audience": "夜職を始めたい、店選びや移籍で悩む女性",
        "purpose": "不安を言語化し、続けられる店や働き方の判断材料を渡す",
        "cta": "必要な場合だけ、相談余地を最後に一言添える",
        "banned": "誇大な収入断定、強い求人、説教、店舗名の羅列",
    },
    "liver_manager": {
        "audience": "配信初心者、伸び悩むライバー、事務所選びで迷う人",
        "purpose": "配信のつまずきを具体化し、今日変えられる行動を示す",
        "cta": "必要な場合だけ、相談余地を最後に一言添える",
        "banned": "楽して稼げる断定、ギフト要求、他社批判、精神論だけの助言",
    },
}


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
    ) -> ProviderResult[dict[str, Any]]:
        if not self.available:
            return ProviderResult(self.provider_name, self.provider_version, "UNAVAILABLE", reason="github_models_not_enabled_or_token_missing")
        rules = ACCOUNT_RULES[account_id]
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
        developer_prompt = (
            "あなたはSNS編集者です。入力された1件の参照投稿だけを根拠に、日本語Threads本文を作成してください。"
            "出力はJSONオブジェクトのみ。元投稿名、URL、source、reference、metadata、transcript、AI、内部処理語を公開文に書かない。"
            "数値・事実・経験を捏造しない。元文の長いコピーを避け、1投稿1テーマ、80〜500文字の自然な読者向け文章にする。"
            "public_post_textの各実質的主張をclaim_supportへ列挙し、source_evidenceは入力中の根拠文を短く正確に引用する。"
            "JSON keys: internal_analysis{main_claims,topic,audience}, public_post_text, claim_support[{caption_claim,source_evidence}], safety_notes, blocked_reasons。"
        )
        user_prompt = json.dumps({
            "account_rules": rules,
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

    It never invents source facts: an account-relevant evidence sentence must
    exist, and the generated public template is still subjected to the same
    semantic and public-post validators as a model result.
    """

    provider_name = "deterministic_grounded_fallback"
    provider_version = "1"

    EVIDENCE_TERMS = {
        "night_scout": ("夜職", "店", "時給", "ノルマ", "客層", "出勤", "移籍", "副業", "相談"),
        "liver_manager": ("配信", "初見", "コメント", "リスナー", "ギフト", "事務所", "継続", "話題"),
    }

    @staticmethod
    def _sentences(text: str) -> list[str]:
        return [item.strip() for item in re.split(r"[。！？!?\n]+", str(text or "")) if item.strip()]

    def generate(
        self,
        post: SourcePostBundle,
        *,
        account_id: str,
        recent_posts: list[str],
        transcript_excerpt: str = "",
    ) -> ProviderResult[dict[str, Any]]:
        signal = "\n".join(filter(None, [transcript_excerpt, post.original_post_text])).strip()
        terms = self.EVIDENCE_TERMS.get(account_id, ())
        evidence_candidates = [sentence for sentence in self._sentences(signal) if any(term in sentence for term in terms)]
        if not evidence_candidates:
            return ProviderResult(self.provider_name, self.provider_version, "UNAVAILABLE", reason="account_relevant_source_evidence_missing")
        evidence = max(evidence_candidates, key=lambda sentence: (sum(term in sentence for term in terms), len(sentence)))[:300]
        try:
            from public_post_quality import generate_grounded_reader_facing_post
        except ImportError:
            return ProviderResult(self.provider_name, self.provider_version, "UNAVAILABLE", reason="public_post_generator_unavailable")
        generated = generate_grounded_reader_facing_post(
            account_id,
            private_signal=signal,
            index=max(1, int(post.content_hash[:4], 16) % 25 + 1) if post.content_hash else 1,
            media_metadata={"media_type": post.media_type},
            recent_posts=recent_posts,
        )
        public_text = str(generated.get("public_post_text", "")).strip()
        public_sentences = self._sentences(public_text)
        if not public_text or not public_sentences:
            return ProviderResult(self.provider_name, self.provider_version, "FAILED", reason="deterministic_caption_empty")
        caption_claim = max(public_sentences, key=lambda sentence: lexical_similarity(sentence, evidence))
        if lexical_similarity(caption_claim, evidence) < 0.08:
            return ProviderResult(self.provider_name, self.provider_version, "BLOCKED", reason="deterministic_claim_not_grounded")
        return ProviderResult(self.provider_name, self.provider_version, "PASS", data={
            "internal_analysis": {
                "main_claims": [evidence],
                "topic": generated.get("grounding_summary", {}).get("topic", ""),
                "audience": ACCOUNT_RULES[account_id]["audience"],
            },
            "public_post_text": public_text,
            "claim_support": [{"caption_claim": caption_claim, "source_evidence": evidence}],
            "safety_notes": "Deterministic source-grounded fallback; raw source stays private.",
            "blocked_reasons": list(generated.get("blocked_reasons", [])),
        })


@dataclass
class SourceGroundedCaptionService:
    generation_provider: Any
    alignment_provider: Any = None
    fallback_provider: Any = None

    def __post_init__(self) -> None:
        if self.alignment_provider is None:
            self.alignment_provider = LocalSemanticAlignmentProvider()
        if self.fallback_provider is None:
            self.fallback_provider = DeterministicGroundedProvider()

    def generate(
        self,
        post: SourcePostBundle,
        *,
        account_id: str,
        recent_posts: list[str] | None = None,
        transcript_excerpt: str = "",
    ) -> dict[str, Any]:
        recent_posts = list(recent_posts or [])
        generated = self.generation_provider.generate(
            post,
            account_id=account_id,
            recent_posts=recent_posts,
            transcript_excerpt=transcript_excerpt,
        )
        primary_failure = generated.reason if not generated.ok else ""
        if (not generated.ok or not generated.data) and self.fallback_provider is not None:
            fallback = self.fallback_provider.generate(
                post,
                account_id=account_id,
                recent_posts=recent_posts,
                transcript_excerpt=transcript_excerpt,
            )
            if fallback.ok and fallback.data:
                generated = fallback
        if not generated.ok or not generated.data:
            return {
                "status": "BLOCKED",
                "public_post_text": "",
                "internal_analysis": {},
                "safety_notes": "",
                "blocked_reasons": [generated.reason or "caption_provider_unavailable"],
                "provider_status": generated.status,
                "primary_provider_failure": primary_failure,
            }
        data = generated.data
        internal = data.get("internal_analysis") if isinstance(data.get("internal_analysis"), dict) else {}
        main_claims = [str(item).strip() for item in internal.get("main_claims", []) if str(item).strip()]
        support = [item for item in data.get("claim_support", []) if isinstance(item, dict)]
        public_text = str(data.get("public_post_text", "")).strip()
        alignment = self.alignment_provider.evaluate(
            source_text="\n".join(filter(None, [post.original_post_text, transcript_excerpt])),
            public_post_text=public_text,
            main_claims=main_claims,
            claim_support=support,
            recent_posts=recent_posts,
        )
        alignment_data = alignment.data or {
            "status": "BLOCKED",
            "blocked_reasons": [alignment.reason or "semantic_alignment_failed"],
        }
        blocked = [str(item) for item in data.get("blocked_reasons", []) if str(item)]
        blocked.extend(alignment_data.get("blocked_reasons", []))
        return {
            "status": "PASS" if not blocked and alignment.status == "PASS" else "BLOCKED",
            "internal_analysis": internal,
            "public_post_text": public_text,
            "claim_support": support,
            "safety_notes": str(data.get("safety_notes", "")),
            "blocked_reasons": sorted(set(blocked)),
            "semantic_alignment": alignment_data,
            "provider_name": generated.provider_name,
            "provider_version": generated.provider_version,
            "provider_status": generated.status,
            "primary_provider_failure": primary_failure,
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
