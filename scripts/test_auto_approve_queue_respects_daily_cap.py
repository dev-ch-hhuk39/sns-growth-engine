#!/usr/bin/env python3
from __future__ import annotations
import importlib.util
import inspect
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("auto_approve_queue", ROOT/"scripts/auto_approve_queue.py")
mod=importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
def main()->int:
    rules={"daily_ready_cap":1,"cooldown_minutes":0}
    now=mod.now_iso()
    ready=[{"queue_id":"q_ready","account_id":"night_scout","status":"READY","auto_ready_at":now}]
    duplicate_log=[{"account_id":"night_scout","operation":"queue_approved","details":"queue_id=q_ready auto_ready=true","timestamp":now}]
    blocked_reason=mod.account_limits_ok("night_scout",{},duplicate_log,ready,rules)

    superseded=[{"queue_id":"q_old","account_id":"night_scout","status":"SUPERSEDED","auto_ready_at":now}]
    superseded_log=[{"account_id":"night_scout","operation":"queue_approved","details":"queue_id=q_old auto_ready=true","timestamp":now}]
    allowed_reason=mod.account_limits_ok("night_scout",{},superseded_log,superseded,rules)

    checks={
        "canonical READY counts once": blocked_reason == (False,"daily_ready_cap_reached"),
        "SUPERSEDED approval does not count": allowed_reason == (True,"ok"),
        "build plan uses canonical queue rows": "account_limits_ok(acct, selected_times, logs, all_queue_rows" in inspect.getsource(mod.build_plan),
    }
    for name,passed in checks.items():
        print(f"  {'PASS' if passed else 'FAIL'} {name}")
    passed_count=sum(checks.values())
    print(f"PASS: {passed_count} / FAIL: {len(checks)-passed_count}")
    return 0 if all(checks.values()) else 1
if __name__=="__main__": raise SystemExit(main())
