#!/usr/bin/env python3
"""Direct-media preparation acquires only bounded X/YouTube source posts."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
workflow = (ROOT / ".github/workflows/direct-media-preparation.yml").read_text(encoding="utf-8")
marker = "- name: Acquire bounded X and YouTube reference posts before media preparation"
assert marker in workflow
step = workflow.split(marker, 1)[1].split("- name: Dry-run direct preparation plan", 1)[0]
assert step.count("acquire_approved_source_posts_failsoft.py") == 2
assert '--platform x' in step
assert '--platform youtube' in step
assert '--platform threads' not in step
assert '--platform tiktok' not in step
assert step.count('--apply --confirm-acquisition') == 2
assert '--reference-only' not in step
print("PASS test_direct_media_acquisition_requires_permission_ledger.py")
