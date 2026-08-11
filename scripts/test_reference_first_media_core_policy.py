#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from generation.media_platform_policy import (  # noqa: E402
    REFERENCE_PLATFORMS,
    REFERENCE_PLATFORM_PRIORITY,
    PHYSICAL_MEDIA_PLATFORMS,
    DEFERRED_PHYSICAL_MEDIA_PLATFORMS,
    can_attempt_physical_media,
    physical_media_provider,
    reference_priority_score,
)
from generation.reference_first_router import load_operational_mix  # noqa: E402
from reference.source_scoring import platform_priority_score  # noqa: E402

assert REFERENCE_PLATFORMS == ("tiktok", "threads", "x", "youtube")
assert REFERENCE_PLATFORM_PRIORITY == {"tiktok": 0, "threads": 1, "x": 2, "youtube": 3}
assert set(PHYSICAL_MEDIA_PLATFORMS) == {"x", "youtube", "tiktok"}
assert set(DEFERRED_PHYSICAL_MEDIA_PLATFORMS) == {"threads"}
assert can_attempt_physical_media("x")
assert can_attempt_physical_media("youtube")
assert not can_attempt_physical_media("threads")
assert can_attempt_physical_media("tiktok")
assert physical_media_provider("x") == "yt_dlp"
assert physical_media_provider("youtube") == "yt_dlp"
assert physical_media_provider("tiktok") == "public_embed_direct_http"
assert reference_priority_score("tiktok") > reference_priority_score("threads") > reference_priority_score("x") > reference_priority_score("youtube")
assert platform_priority_score({"source_platform": "tiktok"}) > platform_priority_score({"source_platform": "threads"}) > platform_priority_score({"source_platform": "x"}) > platform_priority_score({"source_platform": "youtube"})

for account_id in ("night_scout", "liver_manager"):
    mix = load_operational_mix(account_id)
    assert mix["approved_source_clip"] == 5
    assert mix["reference_text_generation"] + mix["direct_reference_media"] == 80

media_cfg = json.loads((ROOT / "config/media_growth_engine.json").read_text(encoding="utf-8"))
assert media_cfg["physical_media_source_platforms"] == ["x", "youtube", "tiktok"]
assert media_cfg["aspect_ratio_policy"] == "preserve_source"
assert media_cfg["target_aspect_ratio"] == "preserve_source"

routing = json.loads((ROOT / "config/source_backend_routing.json").read_text(encoding="utf-8"))
assert routing["routes"]["threads.profile_posts"]["primary"] == "threads_public_http"
assert routing["routes"]["threads.profile_posts"]["fallbacks"] == [
    "threads_search_index",
    "threads_graph_public_discovery",
]
assert "playwright" not in json.dumps(routing["routes"]["threads.profile_posts"])
assert routing["routes"]["threads.post_detail"] == {
    "primary": "threads_oembed_detail",
    "fallbacks": ["threads_public_http"],
    "shadow": [],
    "cooldown_seconds": 900,
    "circuit_failure_threshold": 3,
}
assert routing["routes"]["tiktok.profile_posts"]["fallbacks"] == ["tiktok_gallery_dl"]

workflow = (ROOT / ".github/workflows/direct-media-preparation.yml").read_text(encoding="utf-8")
assert "playwright install" not in workflow
assert "--platform threads" not in workflow
assert "--platform x" in workflow
assert "--platform youtube" in workflow

for workflow_name in ("account-acquisition.yml", "threads-video-reference-preparation.yml"):
    active_workflow = (ROOT / ".github/workflows" / workflow_name).read_text(encoding="utf-8")
    assert "playwright install" not in active_workflow
    assert "THREADS_BROWSER_STORAGE_STATE_B64" not in active_workflow

x_decision = json.loads((ROOT / "docs/x-reusable-media-permission-decision-package.json").read_text(encoding="utf-8"))
assert x_decision["status"] == "OWNER_AUTHORIZED_APPLIED"
assert x_decision["apply"] is True
assert x_decision["permission_ledger_read_after_write"] == "PASS"
assert x_decision["collision_audit"]["status"] == "PASS"

print("PASS test_reference_first_media_core_policy.py")
