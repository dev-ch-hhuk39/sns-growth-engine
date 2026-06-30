#!/usr/bin/env python3
from __future__ import annotations
import importlib.util, os
from pathlib import Path
from types import SimpleNamespace
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("run_autopilot_loop", ROOT/"scripts/run_autopilot_loop.py")
mod=importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
def main()->int:
    old={k:os.environ.get(k) for k in ("PUBLISH_ENABLED","ALLOW_REAL_THREADS_POST")}
    os.environ["PUBLISH_ENABLED"]="true"; os.environ["ALLOW_REAL_THREADS_POST"]="true"
    rules=mod.load_rules(); rules["defaults"]["auto_post_enabled"]=True
    ok=mod.auto_post_gate(SimpleNamespace(auto_post=True,confirm_real_post=True,skip_real_post=False),rules)["allowed"] is True
    for k,v in old.items():
        if v is None: os.environ.pop(k,None)
        else: os.environ[k]=v
    print(f"  {'PASS' if ok else 'FAIL'} triple gate"); print(f"PASS: {1 if ok else 0} / FAIL: {0 if ok else 1}"); return 0 if ok else 1
if __name__=="__main__": raise SystemExit(main())
