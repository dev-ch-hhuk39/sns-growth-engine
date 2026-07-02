#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("run_autonomous_loop", ROOT / "scripts/run_autonomous_loop.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def main() -> int:
    cfg = json.loads((ROOT / "config/autonomous_mode.json").read_text(encoding="utf-8"))
    plan = mod.build_autonomous_plan("all", cfg)
    selected_platforms = {row["source_platform"] for rows in plan["selected_pilot_sources"].values() for row in rows}
    ok = "x" in cfg.get("blocked_platforms_for_fetch", []) and "x" not in selected_platforms and plan["safety"]["x_fetch"] is False
    print(f"  {'PASS' if ok else 'FAIL'} x fetch blocked")
    print(f"PASS: {1 if ok else 0} / FAIL: {0 if ok else 1}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
