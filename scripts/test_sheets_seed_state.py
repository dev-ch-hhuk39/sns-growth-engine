#!/usr/bin/env python3
"""Validate production Sheets recovery seed definitions without network access."""
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
    checks = []

    accounts = {r["account_id"]: r for r in mod.account_rows()}
    categories = mod.category_rows()
    prompts = mod.prompt_rows()
    src_accounts, src_video = mod.source_rows()
    drafts, socials, queues = mod.draft_social_queue_rows()
    learning = mod.learning_rule_rows()

    checks.append(("three accounts", len(accounts) == 3))
    checks.append(("night/liver categories", sum(r["account_id"] == "night_scout" for r in categories) >= 8 and sum(r["account_id"] == "liver_manager" for r in categories) >= 8))
    checks.append(("prompt templates >=5", len(prompts) >= 5))
    checks.append(("source accounts seeded", len(src_accounts) >= 5))
    checks.append(("video sources seeded", len(src_video) >= 2))
    checks.append(("draft/social/queue 6 each", len(drafts) == 6 and len(socials) == 6 and len(queues) == 6))
    checks.append(("learning rules inactive", all(str(r["active"]).lower() == "false" for r in learning)))

    failed = [name for name, ok in checks if not ok]
    for name, ok in checks:
        print(f"  {'PASS' if ok else 'FAIL'} {name}")
    print(f"PASS: {len(checks)-len(failed)} / FAIL: {len(failed)}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
