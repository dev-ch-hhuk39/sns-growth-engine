#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    text = (ROOT / ".github/workflows/autonomous-growth-loop.yml").read_text(encoding="utf-8")
    ok = "kill_switch" in text and "confirm_autonomous" in text
    print(f"  {'PASS' if ok else 'FAIL'} workflow kill switch")
    print(f"PASS: {1 if ok else 0} / FAIL: {0 if ok else 1}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
