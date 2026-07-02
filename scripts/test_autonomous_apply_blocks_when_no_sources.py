#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("run_autonomous_loop", ROOT / "scripts/run_autonomous_loop.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def main() -> int:
    cfg = mod.load_autonomous_config()
    cfg["allowed_platforms_for_fetch"] = []
    plan = mod.build_autonomous_plan("all", cfg)
    ok = plan["status"] == "BLOCKED" and "no_autonomous_source_candidates" in plan["blocked_reasons"]
    print(f"  {'PASS' if ok else 'FAIL'} apply blocks when no sources")
    print(f"PASS: {1 if ok else 0} / FAIL: {0 if ok else 1}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
