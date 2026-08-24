#!/usr/bin/env python3
"""TikTok Shop is complete but credential-pending and review-first."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from accounts.managed_accounts import account_production_enabled, account_status  # noqa: E402
from accounts.tiktok_shop_policy import (  # noqa: E402
    cta_phase,
    requires_human_review,
    validate_evidence,
)
from public_post_quality import final_public_post_validator, generate_production_post  # noqa: E402

account = json.loads((ROOT / "config/accounts/tiktok_shop.json").read_text(encoding="utf-8"))
policy = json.loads((ROOT / "config/tiktok_shop_policy.json").read_text(encoding="utf-8"))
sources = json.loads((ROOT / "config/source_accounts/tiktok_shop_sources.json").read_text(encoding="utf-8"))

assert account_status("tiktok_shop") == "CREDENTIAL_PENDING"
assert not account_production_enabled("tiktok_shop")
assert account["threads_credentials"]["handle"] == ""
assert policy["first_20_posts"]["human_review_required"] is True
assert all(requires_human_review({"content_type": "general_text"}, published_count=index)[0] for index in range(20))
assert cta_phase(beginner_posts=0, creator_posts=0, repeated_pain_count=0) == 1
assert len(sources["sources"]) == 7
assert all(source["target_account_id"] == "tiktok_shop" for source in sources["sources"])
assert all(source.get("media_pipeline_eligible", False) is False for source in sources["sources"])

official_record = {
    "evidence_class": "official_fact",
    "source_url": "https://seller-jp.tiktok.com/",
    "source_publisher": "TikTok Shop Seller Academy",
    "source_date": "2026-08-01",
    "verified_at": "2026-08-24T00:00:00Z",
    "official_status": "official",
    "freshness_status": "FRESH",
    "claim": "official fact",
}
official = validate_evidence(official_record)
assert official["status"] == "PASS"
assert validate_evidence({**official_record, "evidence_class": "market_estimate"})["status"] == "BLOCKED"

for attempt in range(5):
    output = generate_production_post(
        "tiktok_shop",
        batch_id="tiktok_shop_substrate",
        content_type="original_text",
        attempt=attempt,
    )
    assert final_public_post_validator(output["public_post_text"], "tiktok_shop")["status"] == "PASS"

print("PASS: TikTok Shop credential-pending substrate, policy and generation")
