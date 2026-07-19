#!/usr/bin/env python3
"""Media captions never silently become an unrelated deterministic template."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]

from acquisition.contracts import ProviderResult
from acquisition.models import SourcePostBundle
from generation.source_grounded_caption import SourceGroundedCaptionService


class Unavailable:
    provider_name = "unavailable_source_specific_provider"
    provider_version = "test"

    def generate(self, *_args, **_kwargs):
        return ProviderResult(self.provider_name, self.provider_version, "UNAVAILABLE", reason="provider_unavailable")


post = SourcePostBundle(
    source_post_id="sp_test", source_id="src_test", target_account_id="liver_manager",
    platform="threads", profile_url="https://www.threads.com/@creator",
    canonical_post_url="https://www.threads.com/@creator/post/ABC",
    external_post_id="ABC", original_post_text="配信に関する固有の元投稿", published_at="",
)
result = SourceGroundedCaptionService(Unavailable()).generate(post, account_id="liver_manager")
checks = {
    "blocked": result["status"] == "BLOCKED",
    "no generic public text": result["public_post_text"] == "",
    "provider reason retained": "provider_unavailable" in result["blocked_reasons"],
}
for label, ok in checks.items():
    print(f"  {'PASS' if ok else 'FAIL'} {label}")
raise SystemExit(0 if all(checks.values()) else 1)
