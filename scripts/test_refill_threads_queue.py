#!/usr/bin/env python3
"""Validate refill_threads_queue safety constraints without Sheets access."""
from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/refill_threads_queue.py"


def _load():
    spec = importlib.util.spec_from_file_location("refill_threads_queue", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    mod = _load()
    source = SCRIPT.read_text(encoding="utf-8")
    night_title, night_text = mod.text_for("night_scout", "接客", 3)
    liver_title, liver_text = mod.text_for("liver_manager", "ファン化", 3)
    checks = [
        ("allowed accounts", mod.ALLOWED_ACCOUNTS == {"night_scout", "liver_manager"}),
        ("beauty blocked in cli", "beauty_account is draft_only" in source),
        ("x disabled note", "X disabled" in source),
        ("queue threads only", '"platform": "threads"' in source),
        ("no auto publish", '"auto_publish": "false"' in source),
        ("waiting review", '"status": "WAITING_REVIEW"' in source),
        ("dry-run read-only output", "[READ_ONLY]" in source and '"read_only": True' in source),
        ("tone check in plan", '"tone_check"' in source),
        ("night CTA optional", "LINE" in night_text and "DM" in night_text and night_title),
        ("liver CTA optional", "LINE" in liver_text and "DM" in liver_text and liver_title),
    ]
    failed = [name for name, ok in checks if not ok]
    for name, ok in checks:
        print(f"  {'PASS' if ok else 'FAIL'} {name}")
    print(f"PASS: {len(checks)-len(failed)} / FAIL: {len(failed)}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
