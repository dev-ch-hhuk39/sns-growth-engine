#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def main() -> int:
    ns = (ROOT / ".github/workflows/autonomous-growth-loop-night-scout.yml").read_text()
    lm = (ROOT / ".github/workflows/autonomous-growth-loop-liver-manager.yml").read_text()
    ok = "ALLOW_MEDIA_POSTS" not in ns + lm and "run_autonomous_loop.py" in ns + lm
    print(f"  {'PASS' if ok else 'FAIL'} text-only schedule unchanged")
    print(f"PASS: {1 if ok else 0} / FAIL: {0 if ok else 1}")
    return 0 if ok else 1
if __name__ == "__main__":
    raise SystemExit(main())
