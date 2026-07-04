#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    text = (ROOT / ".github/workflows/autonomous-growth-loop-liver-manager.yml").read_text(encoding="utf-8")
    expected = ['cron: "45 0 * * *"', 'cron: "45 3 * * *"', 'cron: "45 6 * * *"', 'cron: "45 8 * * *"', 'cron: "45 11 * * *"']
    ok = all(x in text for x in expected) and "JST 10:00/13:00/16:00/18:00/21:00" in text
    print(f"  {'PASS' if ok else 'FAIL'} liver_manager schedule slots")
    print(f"PASS: {1 if ok else 0} / FAIL: {0 if ok else 1}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
