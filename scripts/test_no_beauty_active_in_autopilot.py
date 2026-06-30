#!/usr/bin/env python3
from __future__ import annotations
import subprocess, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
p=subprocess.run([sys.executable,"scripts/run_autopilot_loop.py","--dry-run","--account-id","beauty_account"],cwd=ROOT,text=True,stdout=subprocess.PIPE)
ok=p.returncode==1 and "BLOCKED" in p.stdout
print(f"  {'PASS' if ok else 'FAIL'} beauty blocked in autopilot"); print(f"PASS: {1 if ok else 0} / FAIL: {0 if ok else 1}")
raise SystemExit(0 if ok else 1)
