#!/usr/bin/env python3
from __future__ import annotations
import importlib.util
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("auto_approve_queue", ROOT/"scripts/auto_approve_queue.py")
mod=importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
def main()->int:
    ok,reason=mod.account_limits_ok("night_scout",{"night_scout":[mod.now_utc()]},[],[],{"daily_ready_cap":2,"cooldown_minutes":180})
    passed=(not ok and reason=="cooldown_not_satisfied")
    print(f"  {'PASS' if passed else 'FAIL'} cooldown"); print(f"PASS: {1 if passed else 0} / FAIL: {0 if passed else 1}"); return 0 if passed else 1
if __name__=="__main__": raise SystemExit(main())
