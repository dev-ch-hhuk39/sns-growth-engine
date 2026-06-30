#!/usr/bin/env python3
from __future__ import annotations
import importlib.util
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("auto_approve_queue", ROOT/"scripts/auto_approve_queue.py")
mod=importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
def main()->int:
    rules=mod.rules_for_account(mod.load_rules(),"night_scout")
    q={"queue_id":"q","account_id":"night_scout","platform":"threads","status":"WAITING_REVIEW","generation_mode":"reference_score_to_threads","media_asset_id":"m1"}
    text="夜職でしんどくなる人ほど、最初に見るべきポイントがある。相談しやすい形に変換する投稿です。"
    ev=mod.evaluate_item(queue=q,draft={"source_refs":"r"},derivative={"text":text},scores_by_ref={"r":{"recommended_use":"REFERENCE_ONLY"}},existing_texts=[],rules=rules)
    ok=ev["status"]=="REJECTED" and "media_not_allowed_for_auto_ready" in ev["reasons"]
    print(f"  {'PASS' if ok else 'FAIL'} media blocked"); print(f"PASS: {1 if ok else 0} / FAIL: {0 if ok else 1}"); return 0 if ok else 1
if __name__=="__main__": raise SystemExit(main())
