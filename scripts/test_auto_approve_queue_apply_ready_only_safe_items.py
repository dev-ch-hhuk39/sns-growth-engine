#!/usr/bin/env python3
from __future__ import annotations
import importlib.util
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("auto_approve_queue", ROOT / "scripts/auto_approve_queue.py")
mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)

class Fake:
    def __init__(self): self.updated=[]; self.bulk_calls=[]; self.logs=[]
    def update_queue_item(self, qid, **fields): self.updated.append((qid, fields))
    def bulk_update_queue_items(self, updates): self.bulk_calls.append(updates); return len(updates)
    def log(self, **kw): self.logs.append(kw)

def main() -> int:
    client=Fake()
    plan={"results":[{"status":"APPROVABLE","queue_id":"q_safe","account_id":"night_scout","quality_score":90,"safety_score":100,"risk_score":0,"score_total":190},{"status":"REJECTED","queue_id":"q_bad","account_id":"night_scout"}]}
    res=mod.apply_ready(client, plan)
    promoted = dict(client.bulk_calls[0])["q_safe"]
    rejected = dict(client.bulk_calls[0])["q_bad"]
    checks=[("only one promoted", res["updated_queue_ids"]==["q_safe"]),("status READY", promoted["status"]=="READY"),("rejected item remains unpromoted", "status" not in rejected),("queue_approved log", client.logs[0]["operation"]=="queue_approved")]
    failed=[n for n,ok in checks if not ok]
    for n,ok in checks: print(f"  {'PASS' if ok else 'FAIL'} {n}")
    print(f"PASS: {len(checks)-len(failed)} / FAIL: {len(failed)}")
    return 1 if failed else 0
if __name__=="__main__": raise SystemExit(main())
