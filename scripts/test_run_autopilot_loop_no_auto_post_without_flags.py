#!/usr/bin/env python3
from __future__ import annotations
import importlib.util
from pathlib import Path
from types import SimpleNamespace
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("run_autopilot_loop", ROOT/"scripts/run_autopilot_loop.py")
mod=importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
def main()->int:
    args=SimpleNamespace(auto_post=True,confirm_real_post=False,skip_real_post=False)
    gate=mod.auto_post_gate(args,mod.load_rules())
    ok=gate["allowed"] is False
    print(f"  {'PASS' if ok else 'FAIL'} no autopost without flags"); print(f"PASS: {1 if ok else 0} / FAIL: {0 if ok else 1}"); return 0 if ok else 1
if __name__=="__main__": raise SystemExit(main())
