#!/usr/bin/env python3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from acquisition.contracts import ProviderResult
from acquisition.models import SourcePostBundle
from generation.source_grounded_caption import SourceGroundedCaptionService


class FixtureProvider:
    provider_name = "fixture"
    provider_version = "1"

    def generate(self, post, *, account_id, recent_posts, transcript_excerpt=""):
        return ProviderResult(self.provider_name, self.provider_version, "PASS", data={
            "internal_analysis": {"main_claims": ["常連だけの会話は初見が参加しづらい"]},
            "public_post_text": "配信に初見さんが来ても、常連だけの会話が続くと入りづらさを感じやすい。\n\n最初に今の話題を一言伝えて、参加のきっかけを作ってみてください。",
            "claim_support": [{"caption_claim": "常連だけの会話が続くと入りづらい", "source_evidence": "常連だけで会話していると参加しづらい"}],
            "safety_notes": "private only",
            "blocked_reasons": [],
        })


post = SourcePostBundle(
    source_post_id="sp_1", source_id="source_1", target_account_id="liver_manager", platform="youtube",
    profile_url="https://youtube.com/@example", canonical_post_url="https://youtube.com/watch?v=abcdefghijk",
    external_post_id="abcdefghijk", original_post_text="配信に初見が入っても、常連だけで会話していると参加しづらい。",
    published_at="",
)
result = SourceGroundedCaptionService(FixtureProvider()).generate(post, account_id="liver_manager")
checks = [
    ("grounded fixture passes alignment", result["status"] == "PASS"),
    ("internal analysis is structurally separate", isinstance(result.get("internal_analysis"), dict)),
    ("private notes never enter public text", "private only" not in result.get("public_post_text", "")),
    ("alignment evidence is recorded", result.get("semantic_alignment", {}).get("status") == "PASS"),
]
for name, ok in checks:
    print(f"  {'PASS' if ok else 'FAIL'} {name}")
failed = [name for name, ok in checks if not ok]
print(f"PASS: {len(checks) - len(failed)} / FAIL: {len(failed)}")
raise SystemExit(1 if failed else 0)
