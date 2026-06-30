#!/usr/bin/env python3
from __future__ import annotations
import subprocess, sys, json, tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def main()->int:
    rules=json.loads((ROOT/"config/auto_approval_rules.json").read_text()); rules["defaults"]["kill_switch"]=True
    p=Path(tempfile.gettempdir())/"auto_rules_kill_switch.json"; p.write_text(json.dumps(rules),encoding="utf-8")
    out=subprocess.run([sys.executable,"scripts/auto_approve_queue.py","--dry-run","--rules-file",str(p)],cwd=ROOT,text=True,stdout=subprocess.PIPE)
    ok="kill_switch" in out.stdout or '"approvable_count": 0' in out.stdout
    print(f"  {'PASS' if ok else 'FAIL'} no auto ready kill switch"); print(f"PASS: {1 if ok else 0} / FAIL: {0 if ok else 1}"); return 0 if ok else 1
if __name__=="__main__": raise SystemExit(main())
