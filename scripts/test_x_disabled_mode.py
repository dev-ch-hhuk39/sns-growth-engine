#!/usr/bin/env python3
"""Validate X is disabled for the recovery operation."""
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
    accounts = {r["account_id"]: r for r in mod.account_rows()}
    prompts = {r["template_id"]: r for r in mod.prompt_rows()}
    _, socials, queues = mod.draft_social_queue_rows()
    src_accounts, _ = mod.source_rows()
    x_sources = [r for r in src_accounts if r["source_platform"] == "x"]
    checks = [
        ("night x disabled", str(accounts["night_scout"]["x_enabled"]).lower() == "false"),
        ("liver x disabled", str(accounts["liver_manager"]["x_enabled"]).lower() == "false"),
        ("x prompts inactive", prompts["night_scout_x"]["active"] == "FALSE" and prompts["liver_manager_x"]["active"] == "FALSE"),
        ("no x queue", all(r["platform"] != "x" for r in queues)),
        ("no x social", all(r["platform"] != "x" for r in socials)),
        ("x source fetch disabled", bool(x_sources) and all(str(r["fetch_enabled"]).lower() == "false" for r in x_sources)),
    ]
    failed = [name for name, ok in checks if not ok]
    for name, ok in checks:
        print(f"  {'PASS' if ok else 'FAIL'} {name}")
    print(f"PASS: {len(checks)-len(failed)} / FAIL: {len(failed)}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
