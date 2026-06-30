#!/usr/bin/env python3
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
src=(ROOT/"scripts/run_autopilot_loop.py").read_text()
ok="fetch_source_posts.py" not in src and "x fetch" not in src.lower()
print(f"  {'PASS' if ok else 'FAIL'} no x fetch in autopilot"); print(f"PASS: {1 if ok else 0} / FAIL: {0 if ok else 1}")
raise SystemExit(0 if ok else 1)
