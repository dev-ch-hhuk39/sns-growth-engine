#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("run_autonomous_loop", ROOT / "scripts/run_autonomous_loop.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def main() -> int:
    plan = mod.build_autonomous_plan("all")
    selected_ids = {r["source_id"] for rows in plan["selected_pilot_sources"].values() for r in rows}
    skipped = {r["source_id"]: r["reason"] for r in plan["excluded_sources"] if "tiktok" in r.get("source_id", "")}
    ok = "tiktok_liver_reference_todo" not in selected_ids and skipped.get("tiktok_liver_reference_todo") == "todo_placeholder"
    print(f"  {'PASS' if ok else 'FAIL'} tiktok placeholder skipped")
    print(f"PASS: {1 if ok else 0} / FAIL: {0 if ok else 1}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
