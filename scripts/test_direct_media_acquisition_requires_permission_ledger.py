#!/usr/bin/env python3
"""Direct-media preparation must acquire only ledger-approved reusable sources."""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
workflow = (ROOT / ".github/workflows/direct-media-preparation.yml").read_text(
    encoding="utf-8"
)

step = workflow.split(
    "- name: Acquire bounded reference posts before media preparation", 1
)[1].split("- name: Dry-run direct preparation plan", 1)[0]

assert "acquire_approved_source_posts_failsoft.py" in step
assert "--apply --confirm-acquisition" in step
assert "--reference-only" not in step

print("PASS test_direct_media_acquisition_requires_permission_ledger.py")
