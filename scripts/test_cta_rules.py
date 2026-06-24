#!/usr/bin/env python3
"""Validate CTA policy for Threads-first recovery."""
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
    checks = [
        ("night CTA LINE_AND_DM", accounts["night_scout"]["cta_type"] == "LINE_AND_DM"),
        ("liver CTA LINE_AND_DM", accounts["liver_manager"]["cta_type"] == "LINE_AND_DM"),
        ("beauty CTA NONE", accounts["beauty_account"]["cta_type"] == "NONE"),
        ("night prompt mentions LINE/DM", "LINE" in prompts["night_scout_threads"]["prompt_text"] and "DM" in prompts["night_scout_threads"]["prompt_text"]),
        ("liver prompt mentions LINE/DM", "LINE" in prompts["liver_manager_threads"]["prompt_text"] and "DM" in prompts["liver_manager_threads"]["prompt_text"]),
        ("beauty prompt CTA none", "CTAなし" in prompts["beauty_draft_only"]["prompt_text"]),
    ]
    failed = [name for name, ok in checks if not ok]
    for name, ok in checks:
        print(f"  {'PASS' if ok else 'FAIL'} {name}")
    print(f"PASS: {len(checks)-len(failed)} / FAIL: {len(failed)}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
