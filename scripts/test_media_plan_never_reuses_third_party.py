#!/usr/bin/env python3
from __future__ import annotations
import importlib.util
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("plan_media_mix", ROOT/"scripts/plan_media_mix.py")
mod=importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
ok=not mod.is_media_candidate({"media_asset_id":"m","rights_status":"unknown","media_reuse_risk":"high"})
print(f"  {'PASS' if ok else 'FAIL'} no third-party reuse"); print(f"PASS: {1 if ok else 0} / FAIL: {0 if ok else 1}")
raise SystemExit(0 if ok else 1)
