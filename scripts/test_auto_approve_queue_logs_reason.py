#!/usr/bin/env python3
from __future__ import annotations
import importlib.util
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("auto_approve_queue", ROOT/"scripts/auto_approve_queue.py")
mod=importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
class F:
    def __init__(self): self.logs=[]; self.updated=[]
    def update_queue_item(self,qid,**fields): self.updated.append(fields)
    def log(self,**kw): self.logs.append(kw)
def main()->int:
    f=F(); mod.apply_ready(f,{"results":[{"status":"APPROVABLE","queue_id":"q","account_id":"night_scout","quality_score":90,"safety_score":95,"risk_score":0,"score_total":185}]})
    ok="auto_ready=true" in f.logs[0]["details"] and "AUTO_READY" in f.updated[0]["auto_ready_reason"]
    print(f"  {'PASS' if ok else 'FAIL'} logs reason"); print(f"PASS: {1 if ok else 0} / FAIL: {0 if ok else 1}"); return 0 if ok else 1
if __name__=="__main__": raise SystemExit(main())
