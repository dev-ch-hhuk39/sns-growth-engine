#!/usr/bin/env python3
from __future__ import annotations
import importlib.util
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("plan_media_mix", ROOT/"scripts/plan_media_mix.py")
mod=importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
plan=mod.build_media_mix_plan([{"queue_id":"q1","platform":"threads","status":"WAITING_REVIEW"},{"queue_id":"q2","platform":"threads","status":"WAITING_REVIEW","media_asset_id":"m","rights_status":"allowed","media_reuse_risk":"low"}])
ok=plan["target_text_only_ratio"]==0.70 and plan["target_media_ratio"]==0.30 and plan["media_candidate_count"]==1
print(f"  {'PASS' if ok else 'FAIL'} media mix ratio"); print(f"PASS: {1 if ok else 0} / FAIL: {0 if ok else 1}")
raise SystemExit(0 if ok else 1)
