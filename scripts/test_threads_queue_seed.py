#!/usr/bin/env python3
"""Validate Threads queue recovery seeds."""
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
    _, socials, queues = mod.draft_social_queue_rows()
    checks = [
        ("night queue 3", sum(r["account_id"] == "night_scout" for r in queues) == 3),
        ("liver queue 3", sum(r["account_id"] == "liver_manager" for r in queues) == 3),
        ("beauty queue 0", sum(r["account_id"] == "beauty_account" for r in queues) == 0),
        ("all queues threads", all(r["platform"] == "threads" for r in queues)),
        ("no auto publish", all(str(r["auto_publish"]).lower() == "false" for r in queues)),
        ("social text policy pass", all(r["text_policy_status"] == "PASS" for r in socials)),
    ]
    failed = [name for name, ok in checks if not ok]
    for name, ok in checks:
        print(f"  {'PASS' if ok else 'FAIL'} {name}")
    print(f"PASS: {len(checks)-len(failed)} / FAIL: {len(failed)}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
