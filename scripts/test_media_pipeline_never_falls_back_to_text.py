#!/usr/bin/env python3
"""Direct and clip media runners must preserve media-only scheduled slots."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

direct = (ROOT / "scripts" / "run_direct_reference_media_pipeline.py").read_text(encoding="utf-8")
clip = (ROOT / "scripts" / "run_media_production_pipeline.py").read_text(encoding="utf-8")
workflows = "\n".join(
    path.read_text(encoding="utf-8")
    for path in (ROOT / ".github" / "workflows").glob("*media*.yml")
)

assert "--fallback-to-text" not in direct
assert "--fallback-to-text" not in clip
assert "run_slot_text_fallback" not in direct
assert "run_slot_text_fallback" not in clip
assert "SKIPPED_NO_VALID_MEDIA" in direct
assert "SKIPPED_NO_VALID_MEDIA" in clip
assert "--fallback-to-text" not in workflows

print("PASS test_media_pipeline_never_falls_back_to_text.py")
