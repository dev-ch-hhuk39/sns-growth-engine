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
    source = (ROOT / "scripts/run_autonomous_loop.py").read_text(encoding="utf-8")
    ok = (
        plan["gate_summary"]["daily_post_cap_per_account"] == 5
        and plan["gate_summary"]["daily_ready_cap_per_account"] == 8
        and plan["gate_summary"]["max_posts_per_run"] == 1
        and set(plan["daily_cap_state"]) == {"night_scout", "liver_manager"}
        and "max_posts_per_run_reached_before_account_apply" in source
    )
    print(f"  {'PASS' if ok else 'FAIL'} daily caps allow five scheduled posts")
    print(f"PASS: {1 if ok else 0} / FAIL: {0 if ok else 1}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
