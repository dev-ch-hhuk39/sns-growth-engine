#!/usr/bin/env python3
"""Preparation-only jobs report missing inventory without pretending a post failed."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "src")]

from run_direct_reference_media_pipeline import normalize_prepare_only_outcome

blocked = {"status": "BLOCKED", "blocked_reasons": ["media_content_understanding_missing"]}
prepared = normalize_prepare_only_outcome(blocked, prepare_only=True)
dispatch = normalize_prepare_only_outcome(blocked, prepare_only=False)

assert prepared["status"] == "NO_READY_MEDIA", prepared
assert prepared["preparation_status"] == "BLOCKED", prepared
assert prepared["would_post"] is False, prepared
assert dispatch == blocked, dispatch
print("PASS test_direct_media_prepare_no_ready_is_successful.py")
