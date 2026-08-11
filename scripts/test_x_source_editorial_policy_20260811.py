#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "src")]

from acquire_approved_source_posts import selected_sources  # noqa: E402
from generation.media_platform_policy import (  # noqa: E402
    is_retired_source,
    select_x_video_primary_sources,
)

sources = json.loads((ROOT / "config/source_accounts/default_sources.json").read_text(encoding="utf-8"))["sources"]
by_handle = {str(row.get("source_handle") or "").lower(): row for row in sources}
selected = select_x_video_primary_sources(sources)
selected_handles = [str(row.get("source_handle") or "").lower() for row in selected]
retired = {"@onigiriscout_0", "@cabalounge", "@kyabataihendane"}
text_image_only = {"@takashimaanna", "@minatoku789", "@1okukure_", "@urarament", "@kyaba_career"}
_, tiktok_blocked = selected_sources("liver_manager", "tiktok", reference_only=True)
checks = {
    "only two video primary sources": selected_handles == ["@3j2c9q", "@amuxamudaily"],
    "retired sources marked and excluded": all(is_retired_source(by_handle[h]) and h not in selected_handles for h in retired),
    "text image sources cannot become video candidates": all(by_handle[h].get("x_video_candidate_enabled") is False and h not in selected_handles for h in text_image_only),
    "editorial selection does not infer permission": all("permission_status" not in row or row.get("permission_status") != "approved" for row in selected),
    "retired X does not pollute TikTok results": not tiktok_blocked,
}
for name, ok in checks.items():
    print(f"{'PASS' if ok else 'FAIL'} {name}")
raise SystemExit(0 if all(checks.values()) else 1)
