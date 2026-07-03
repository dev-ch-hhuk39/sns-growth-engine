#!/usr/bin/env python3
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    p = subprocess.run([sys.executable, "scripts/run_autonomous_loop.py", "--account-id", "all", "--dry-run"], cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    ok = p.returncode == 0 and "public_post_preview" in p.stdout and '"would_post": false' in p.stdout and "internal_analysis" not in p.stdout
    print(f"  {'PASS' if ok else 'FAIL'} dry-run shows public preview only")
    print(f"PASS: {1 if ok else 0} / FAIL: {0 if ok else 1}")
    if not ok:
        print(p.stdout[-1200:])
        print(p.stderr[-1200:])
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
