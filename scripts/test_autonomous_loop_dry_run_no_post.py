#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    p = subprocess.run([sys.executable, "scripts/run_autonomous_loop.py", "--account-id", "all", "--dry-run"], cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    data = json.loads(p.stdout)
    ok = p.returncode == 0 and data["mode"] == "dry-run" and data["auto_post_plan"]["enabled"] is True and all(r.get("returncode") == 0 for r in data["results"]) and data["safety"]["x_post"] is False
    print(f"  {'PASS' if ok else 'FAIL'} dry-run no post")
    print(f"PASS: {1 if ok else 0} / FAIL: {0 if ok else 1}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
