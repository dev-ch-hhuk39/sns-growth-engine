#!/usr/bin/env python3
"""Validate beauty_account stays blocked in recovery seeds."""
from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/recover_production_sheets_threads_first.py"


def _load():
    spec = importlib.util.spec_from_file_location("recover", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    mod = _load()
    beauty = {r["account_id"]: r for r in mod.account_rows()}["beauty_account"]
    src_accounts, _ = mod.source_rows()
    beauty_sources = [r for r in src_accounts if r["target_account_ids"] == "beauty_account"]
    process_source = (ROOT / "scripts/process_threads_queue.py").read_text(encoding="utf-8")
    refill_source = (ROOT / "scripts/refill_threads_queue.py").read_text(encoding="utf-8")
    worker_workflow = (ROOT / ".github/workflows/threads-queue-worker.yml").read_text(encoding="utf-8")
    checks = [
        ("beauty inactive", str(beauty["active"]).lower() == "false"),
        ("beauty draft_only", beauty["status"] == "draft_only"),
        ("beauty threads disabled", str(beauty["threads_enabled"]).lower() == "false"),
        ("beauty no CTA", beauty["cta_type"] == "NONE"),
        ("beauty sources blocked", bool(beauty_sources) and all(str(r["blocked"]).lower() == "true" for r in beauty_sources)),
        ("beauty no media actions", all(str(r[k]).lower() == "false" for r in beauty_sources for k in ["allow_download", "allow_cut", "allow_upload"])),
        ("queue worker blocks beauty", "beauty_account is blocked" in process_source),
        ("refill blocks beauty", "beauty_account is draft_only" in refill_source),
        ("workflow has no beauty option", '"beauty_account"' not in worker_workflow),
    ]
    failed = [name for name, ok in checks if not ok]
    for name, ok in checks:
        print(f"  {'PASS' if ok else 'FAIL'} {name}")
    print(f"PASS: {len(checks)-len(failed)} / FAIL: {len(failed)}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
