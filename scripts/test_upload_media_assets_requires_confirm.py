#!/usr/bin/env python3
import subprocess, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
p=subprocess.run([sys.executable,"scripts/upload_media_assets.py","--account-id","night_scout","--upload"],cwd=ROOT,text=True,capture_output=True)
checks=[("nonzero", p.returncode==1), ("confirm mentioned", "confirm_upload=False" in p.stdout or "confirm" in p.stdout)]
bad=[n for n,o in checks if not o]
for n,o in checks: print(f"  {'PASS' if o else 'FAIL'} {n}")
print(f"PASS: {len(checks)-len(bad)} / FAIL: {len(bad)}")
raise SystemExit(1 if bad else 0)
