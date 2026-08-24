#!/usr/bin/env python3
"""Direct-media preparation acquires bounded, ledger-gated source posts."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
workflow = (ROOT / ".github/workflows/direct-media-preparation.yml").read_text(encoding="utf-8")
marker = "- name: Acquire bounded approved reference posts before media preparation"
assert marker in workflow
step = workflow.split(marker, 1)[1].split("- name: Dry-run direct preparation plan", 1)[0]
assert step.count("acquire_approved_source_posts_failsoft.py") == 1
assert '--platform all' in step
assert step.count('--apply --confirm-acquisition') == 1
assert '--reference-only' not in step
assert '--media-filter video-only' in step
assert '--force-backfill' in step
print("PASS test_direct_media_acquisition_requires_permission_ledger.py")
