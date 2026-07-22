#!/usr/bin/env python3
"""Media clip generation must not multiply remote-model latency per window."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from acquisition.contracts import ProviderResult
from acquisition.models import SourcePostBundle
from generation.source_grounded_caption import SourceGroundedCaptionService


class BlockingAlignmentProvider:
    provider_name = "blocking_fixture"
    provider_version = "1"

    def __init__(self) -> None:
        self.calls = 0

    def generate(self, *_args, **_kwargs):
        self.calls += 1
        return ProviderResult(self.provider_name, self.provider_version, "PASS", data={
            "internal_analysis": {"main_claims": ["根拠のない主張"]},
            "public_post_text": "配信について考えてみましょう。",
            "claim_support": [{"caption_claim": "根拠のない主張", "source_evidence": "存在しない根拠"}],
            "blocked_reasons": [],
        })


provider = BlockingAlignmentProvider()
post = SourcePostBundle(
    source_post_id="sp_bounded", source_id="source_bounded", target_account_id="liver_manager", platform="youtube",
    profile_url="https://youtube.com/channel/allowed", canonical_post_url="https://youtube.com/watch?v=bounded",
    external_post_id="bounded", original_post_text="初見が入りやすい配信では、最初に話題を伝える。", published_at="",
)
service = SourceGroundedCaptionService(provider, retry_primary_on_alignment_failure=False)
service.generate(post, account_id="liver_manager", transcript_excerpt=post.original_post_text)
config = json.loads((ROOT / "config/media_growth_engine.json").read_text())
engine = (ROOT / "scripts/run_media_growth_engine.py").read_text()
checks = [
    ("media service has one remote attempt when alignment blocks", provider.calls == 1),
    ("remote captions capped per video", config.get("max_remote_caption_generations_per_video") == 1),
    ("remote captions capped across a whole run", config.get("max_remote_caption_generations_per_run") == 1),
    ("remote timeout stays bounded", 10 <= int(config.get("remote_caption_timeout_seconds", 0)) <= 30),
    ("remaining clip windows use deterministic fallback", "deterministic_caption_service" in engine and "remote_caption_generation_count < remote_caption_run_limit" in engine),
]
for name, ok in checks:
    print(f"  {'PASS' if ok else 'FAIL'} {name}")
raise SystemExit(0 if all(ok for _, ok in checks) else 1)
