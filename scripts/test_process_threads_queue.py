#!/usr/bin/env python3
"""Validate process_threads_queue safety defaults without network access."""
from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/process_threads_queue.py"


def _load():
    spec = importlib.util.spec_from_file_location("process_threads_queue", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    mod = _load()
    source = SCRIPT.read_text(encoding="utf-8")
    class FakeClient:
        def __init__(self):
            self.rows = [
                {"queue_id": "old", "account_id": "beauty_account", "platform": "threads", "status": "READY", "slot_id": "beauty_1130", "business_date_jst": "2026-08-22"},
                {"queue_id": "current", "account_id": "beauty_account", "platform": "threads", "status": "READY", "slot_id": "beauty_1130", "business_date_jst": "2026-08-23"},
                {"queue_id": "wrong-slot", "account_id": "beauty_account", "platform": "threads", "status": "READY", "slot_id": "beauty_2030", "business_date_jst": "2026-08-23"},
            ]

        def _ws(self, _logical):
            return self

        def get_all_records(self):
            return self.rows

    exact = mod.select_candidates(
        FakeClient(), "beauty_account", 1, slot_id="beauty_1130", business_date_jst="2026-08-23"
    )
    checks = [
        ("eligible statuses READY only", mod.ELIGIBLE_STATUSES == {"READY"}),
        ("waiting_review not eligible", "WAITING_REVIEW" not in mod.ELIGIBLE_STATUSES),
        ("planned not eligible", "PLANNED" not in mod.ELIGIBLE_STATUSES),
        ("final statuses skipped", {"POSTED", "PROCESSING", "FAILED", "POSTED_SAVE_FAILED"}.issubset(mod.FINAL_OR_LOCKED_STATUSES)),
        ("beauty has dedicated production gate", "beauty_publish_gate" in source and "BEAUTY_PRODUCTION_ENABLED" in source),
        ("threads only selector", 'platform != "threads"' in source),
        ("real requires confirm", "--confirm-real-post required" in source),
        ("real requires env flags", "PUBLISH_ENABLED" in source and "ALLOW_REAL_THREADS_POST" in source),
        ("posted save fallback", "POSTED_SAVE_FAILED" in source and "posted_results_fallback" in source),
        ("pdca waiting review", "WAITING_REVIEW" in source and "auto_apply=false" in source),
        ("dry-run read-only output", "[READ_ONLY]" in source and '"read_only": True' in source),
        ("exact Beauty slot and date selection", [row["queue_id"] for row in exact] == ["current"]),
    ]
    failed = [name for name, ok in checks if not ok]
    for name, ok in checks:
        print(f"  {'PASS' if ok else 'FAIL'} {name}")
    print(f"PASS: {len(checks)-len(failed)} / FAIL: {len(failed)}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
