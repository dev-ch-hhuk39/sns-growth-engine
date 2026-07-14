#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sheets_client import TAB_DEFINITIONS, TAB_DISPLAY_NAMES


REQUIRED = {
    "media_post_results": {"media_post_result_id", "result_id", "clip_candidate_id", "media_asset_id", "metrics_status", "post_url"},
    "media_metrics": {"media_metrics_id", "media_post_result_id", "clip_candidate_id", "metrics_status", "views", "retention_proxy"},
    "clip_performance": {"clip_performance_id", "media_post_result_id", "clip_candidate_id", "subtitle_style", "status"},
}

checks = []
for tab, columns in REQUIRED.items():
    checks.append((f"{tab} is a Sheets tab", tab in TAB_DEFINITIONS))
    checks.append((f"{tab} has display name", tab in TAB_DISPLAY_NAMES))
    checks.append((f"{tab} has required columns", columns <= set(TAB_DEFINITIONS.get(tab, []))))

failed = [name for name, ok in checks if not ok]
for name, ok in checks:
    print(f"  {'PASS' if ok else 'FAIL'} {name}")
print(f"PASS: {len(checks) - len(failed)} / FAIL: {len(failed)}")
raise SystemExit(1 if failed else 0)
