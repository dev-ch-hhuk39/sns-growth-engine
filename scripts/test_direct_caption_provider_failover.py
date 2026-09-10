#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "src")]

from acquisition.contracts import ProviderResult  # noqa: E402
from acquisition.models import SourcePostBundle  # noqa: E402
from evidence_context_caption import (  # noqa: E402
    DirectCaptionProviderFailover,
    PrivacyBoundedGeminiGroundedProvider,
)
from gemini_hybrid_client import GeminiHttpError  # noqa: E402
from run_media_production_pipeline import _default_final_caption_service  # noqa: E402


class Provider:
    def __init__(self, name: str, status: str) -> None:
        self.provider_name = name
        self.provider_version = "fixture"
        self.status = status
        self.available = True
        self.calls = 0

    def generate(self, *_args, **_kwargs):
        self.calls += 1
        if self.status != "PASS":
            return ProviderResult(
                self.provider_name,
                self.provider_version,
                self.status,
                reason=f"{self.provider_name}_failed",
                retryable=True,
            )
        return ProviderResult(
            self.provider_name,
            self.provider_version,
            "PASS",
            data={
                "internal_analysis": {"main_claims": ["保湿は一つずつ試す"]},
                "public_post_text": "スキンケアは一度に全部変えず、まず一つ試して肌の反応を見てみてほしい。",
                "claim_support": [{"caption_claim": "一つ試す", "source_evidence": "一つずつ試す"}],
                "blocked_reasons": [],
            },
        )


class GeminiClient:
    api_key = "fixture-key"

    def __init__(self) -> None:
        self.prompt = ""

    def generate_json(self, **kwargs):
        self.prompt = str(kwargs["prompt"])
        self.schema = kwargs["schema"]
        return {
            "model": "fixture-gemini",
            "data": {
                "internal_analysis": {"main_claims": ["保湿は一つずつ試す"]},
                "public_post_text": "保湿アイテムは一つずつ試して、肌の反応を見てみてほしい。",
                "claim_support": [{"caption_claim": "一つずつ試す", "source_evidence": "一つずつ試す"}],
                "safety_notes": "",
                "blocked_reasons": [],
            },
        }


post = SourcePostBundle(
    source_post_id="sp_beauty_failover",
    source_id="src_beauty_failover",
    target_account_id="beauty_account",
    platform="tiktok",
    profile_url="https://www.tiktok.com/@fixture",
    canonical_post_url="https://www.tiktok.com/@fixture/video/123",
    external_post_id="123",
    original_post_text="スキンケアは一つずつ試す。",
    published_at="",
)
primary = Provider("github_models", "FAILED")
fallback = Provider("gemini_direct_caption", "PASS")
result = DirectCaptionProviderFailover(primary=primary, fallback=fallback).generate(
    post,
    account_id="beauty_account",
    recent_posts=["外部送信禁止の直近本文"],
    transcript_excerpt="外部送信禁止の文字起こし",
    source_mode="transform",
)
client = GeminiClient()
privacy_result = PrivacyBoundedGeminiGroundedProvider(client=client).generate(
    post,
    account_id="beauty_account",
    recent_posts=["送信禁止の直近投稿"],
    transcript_excerpt="送信禁止の文字起こし",
    source_mode="transform",
)


class FailingClient(GeminiClient):
    def __init__(self, error, recover=False):
        super().__init__()
        self.error = error
        self.recover = recover
        self.models = []

    def generate_json(self, **kwargs):
        self.models.append(kwargs["model"])
        if len(self.models) == 1 or not self.recover:
            raise self.error
        return super().generate_json(**kwargs)


transient = FailingClient(GeminiHttpError(503, "private-body"), recover=True)
transient_result = PrivacyBoundedGeminiGroundedProvider(client=transient).generate(
    post, account_id="beauty_account", recent_posts=[],
)
terminal_cases = []
for error in (GeminiHttpError(400, "secret-key"), GeminiHttpError(403, "secret-key"), RuntimeError("hybrid_ai_budget_blocked:daily_limit_exceeded")):
    failed = FailingClient(error)
    failed_result = PrivacyBoundedGeminiGroundedProvider(client=failed).generate(
        post, account_id="beauty_account", recent_posts=[],
    )
    terminal_cases.append(len(failed.models) == 1 and not failed_result.ok and not failed_result.retryable and "secret-key" not in str(failed_result))
unavailable = FailingClient(GeminiHttpError(429, "private-body"))
exhausted = PrivacyBoundedGeminiGroundedProvider(client=unavailable).generate(
    post, account_id="beauty_account", recent_posts=[],
)

checks = [
    ("primary is attempted once", primary.calls == 1),
    ("Gemini fallback is attempted once", fallback.calls == 1),
    ("fallback provider identity is preserved", result.ok and result.provider_name == "gemini_direct_caption"),
    ("bounded provider returns a usable result", privacy_result.ok),
    ("source post text is included", post.original_post_text in client.prompt),
    ("transcript is excluded", "送信禁止の文字起こし" not in client.prompt),
    ("recent history is excluded", "送信禁止の直近投稿" not in client.prompt),
    ("clip uses the same real provider failover", isinstance(_default_final_caption_service().generation_provider, DirectCaptionProviderFailover)),
    ("transient error switches to existing secondary model", transient_result.ok and transient.models == ["gemini-3.5-flash", "gemini-3.1-flash-lite"]),
    ("auth schema and budget failures never model-hop", all(terminal_cases)),
    ("all-provider failure is bounded and never a PASS", not exhausted.ok and len(unavailable.models) == 2 and "http_429" in exhausted.reason),
    ("analysis response schema defines actual fields", "main_claims" in client.schema["properties"]["internal_analysis"]["properties"]),
]
for name, passed in checks:
    print(f"  {'PASS' if passed else 'FAIL'} {name}")
raise SystemExit(0 if all(passed for _, passed in checks) else 1)
