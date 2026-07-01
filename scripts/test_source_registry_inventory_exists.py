#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
doc = ROOT / "docs/source-registry-inventory.md"
text = doc.read_text(encoding="utf-8") if doc.exists() else ""
required = [
    "platform",
    "source_url",
    "source_type",
    "target_account_id",
    "usage_scope",
    "rights_status",
    "fetch_enabled",
    "manual_only",
    "transcript_enabled",
    "clip_enabled",
    "media_pipeline_eligible",
    "collection_method",
    "current_status",
    "notes",
]
checks = [("exists", doc.exists())] + [(f"header {c}", c in text) for c in required]
bad = [n for n, ok in checks if not ok]
for n, ok in checks:
    print(f"  {'PASS' if ok else 'FAIL'} {n}")
print(f"PASS: {len(checks)-len(bad)} / FAIL: {len(bad)}")
raise SystemExit(1 if bad else 0)
