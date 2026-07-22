#!/usr/bin/env python3
"""Validate posted_results schema and recovery verification constraints."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RECOVER = ROOT / "scripts/recover_production_sheets_threads_first.py"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    sheets = _load(ROOT / "src/sheets_client.py", "sheets_client")
    recover = _load(RECOVER, "recover")
    headers = sheets.TAB_DEFINITIONS["posted_results"]
    row = recover.posted_result_recovery_row()
    source = RECOVER.read_text(encoding="utf-8")
    required = [
        "queue_id", "derivative_id", "platform", "external_post_id", "post_url",
        "status", "metrics_status", "real_post", "media_used", "posted_text",
        "source_queue_status", "save_source", "created_by",
    ]
    checks = [
        ("required columns", all(col in headers for col in required)),
        ("recovery row metrics", row["metrics_status"] == "MANUAL_PENDING"),
        ("recovery row platform", row["platform"] == "threads"),
        ("recovery row safe status", row["status"] == "RECOVERED"),
        ("strict metrics set", 'allowed_metrics = {"PENDING", "MEASURED", "MANUAL_PENDING", "PARTIAL", "UNAVAILABLE"}' in source),
        ("post_url strictness", "posted_rows_have_post_url_or_permalink_pending" in source),
        ("real/media strictness", "posted_real_post_true" in source and "posted_media_used_false" in source),
        ("queue consistency check", "queue_posted_has_posted_result" in source and "posted_queue_id_consistent" in source),
        ("duplicate text check", "posted_duplicate_text_absent" in source),
    ]
    failed = [name for name, ok in checks if not ok]
    for name, ok in checks:
        print(f"  {'PASS' if ok else 'FAIL'} {name}")
    print(f"PASS: {len(checks)-len(failed)} / FAIL: {len(failed)}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
