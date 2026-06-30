#!/usr/bin/env python3
from __future__ import annotations
import importlib.util
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("auto_approve_queue", ROOT/"scripts/auto_approve_queue.py")
mod=importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
def main()->int:
    rules={"daily_ready_cap":1,"cooldown_minutes":0}
    q=[{"account_id":"night_scout","auto_ready_at":mod.now_iso()}]
    ok,reason=mod.account_limits_ok("night_scout",{},[],q,rules)
    passed=(not ok and reason=="daily_ready_cap_reached")
    print(f"  {'PASS' if passed else 'FAIL'} daily cap"); print(f"PASS: {1 if passed else 0} / FAIL: {0 if passed else 1}"); return 0 if passed else 1
if __name__=="__main__": raise SystemExit(main())
