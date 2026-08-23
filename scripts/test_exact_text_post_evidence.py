#!/usr/bin/env python3
"""Focused contract for bounded post-publish evidence verification."""
from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/recover_production_sheets_threads_first.py"


class Client:
    def __init__(self, rows):
        self.rows = rows

    def _ws(self, logical):
        rows = self.rows[logical]

        class Worksheet:
            def get_all_records(self):
                return rows

        return Worksheet()


def load_module():
    spec = importlib.util.spec_from_file_location("recovery_post_evidence", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def main() -> int:
    module = load_module()
    rows = {
        "queue": [{"queue_id": "q1", "account_id": "liver_manager", "platform": "threads", "status": "POSTED"}],
        "posted_results": [{
            "result_id": "r1", "queue_id": "q1", "account_id": "liver_manager",
            "platform": "threads", "external_post_id": "p1", "post_url": "https://www.threads.com/post/p1",
            "verification_status": "READ_AFTER_WRITE_PASS",
        }],
        "metrics_collection_jobs": [
            {"result_id": "r1", "window_hours": window}
            for window in ("24", "72", "168")
        ],
    }
    result = module.verify_exact_text_post_evidence(Client(rows), queue_id="q1", account_id="liver_manager")
    assert result["failed"] == []
    assert result["verification_scope"]["status"] == "PASS"
    assert result["counts"]["exact_metrics_collection_jobs"] == 3

    rows["metrics_collection_jobs"] = rows["metrics_collection_jobs"][:2]
    blocked = module.verify_exact_text_post_evidence(Client(rows), queue_id="q1", account_id="liver_manager")
    assert "metric_windows_24_72_168_scheduled" in blocked["failed"]
    print("PASS: exact text post evidence is bounded and fail-closed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
