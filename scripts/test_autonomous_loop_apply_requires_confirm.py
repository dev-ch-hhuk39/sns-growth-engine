#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    p = subprocess.run([sys.executable, "scripts/run_autonomous_loop.py", "--account-id", "all", "--apply"], cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    data = json.loads(p.stdout)
    ok = p.returncode == 1 and data["status"] == "BLOCKED" and "--apply requires --confirm-autonomous" in data["blocked_reasons"]
    print(f"  {'PASS' if ok else 'FAIL'} apply requires confirm")
    print(f"PASS: {1 if ok else 0} / FAIL: {0 if ok else 1}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
