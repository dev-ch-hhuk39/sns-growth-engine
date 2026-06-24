#!/usr/bin/env python3
"""Validate strict posted_results checks exist in the live verifier."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/recover_production_sheets_threads_first.py"


def main() -> int:
    source = SCRIPT.read_text(encoding="utf-8")
    checks = [
        ("external post id check", "posted_rows_have_external_post_id" in source),
        ("post url or permalink pending check", "posted_rows_have_post_url_or_permalink_pending" in source),
        ("platform threads check", "posted_rows_platform_threads" in source),
        ("metrics status check", "posted_metrics_status_allowed" in source),
        ("real_post true check", "posted_real_post_true" in source),
        ("media_used false check", "posted_media_used_false" in source),
        ("queue posted result check", "queue_posted_has_posted_result" in source),
        ("posted save failed warning", "posted_save_failed_count" in source),
        ("duplicate posted text check", "posted_duplicate_text_absent" in source),
        ("recovered distinction", "RECOVERED" in source and "posted_threads" in source),
    ]
    failed = [name for name, ok in checks if not ok]
    for name, ok in checks:
        print(f"  {'PASS' if ok else 'FAIL'} {name}")
    print(f"PASS: {len(checks)-len(failed)} / FAIL: {len(failed)}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
