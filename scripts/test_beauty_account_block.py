#!/usr/bin/env python3
"""Validate Beauty publication stays gated while Voice sources are read-only."""
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
    voice_profile = mod.json.loads((ROOT / "config/beauty_voice_profile.json").read_text(encoding="utf-8"))
    voice_ids = set(voice_profile["voice_reference_source_ids"])
    process_source = (ROOT / "scripts/process_threads_queue.py").read_text(encoding="utf-8")
    refill_source = (ROOT / "scripts/refill_threads_queue.py").read_text(encoding="utf-8")
    worker_workflow = (ROOT / ".github/workflows/threads-queue-worker.yml").read_text(encoding="utf-8")
    checks = [
        ("beauty inactive", str(beauty["active"]).lower() == "false"),
        ("beauty draft_only", beauty["status"] == "draft_only"),
        ("beauty threads disabled", str(beauty["threads_enabled"]).lower() == "false"),
        ("beauty no CTA", beauty["cta_type"] == "NONE"),
        ("beauty voice sources bounded", {
            r["source_id"] for r in beauty_sources if str(r["fetch_enabled"]).lower() == "true"
        } == voice_ids),
        ("beauty source media reuse blocked", all(str(r["can_reuse_media"]).lower() == "false" for r in beauty_sources)),
        ("beauty no media actions", all(str(r[k]).lower() == "false" for r in beauty_sources for k in ["allow_download", "allow_cut", "allow_upload"])),
        ("queue worker has dedicated beauty gate", "beauty_publish_gate" in process_source and "BEAUTY_PRODUCTION_ENABLED" in process_source),
        ("refill blocks beauty", "beauty_account is draft_only" in refill_source),
        ("workflow beauty option remains explicitly gated", '"beauty_account"' in worker_workflow and "confirm_real_post" in worker_workflow),
    ]
    failed = [name for name, ok in checks if not ok]
    for name, ok in checks:
        print(f"  {'PASS' if ok else 'FAIL'} {name}")
    print(f"PASS: {len(checks)-len(failed)} / FAIL: {len(failed)}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
