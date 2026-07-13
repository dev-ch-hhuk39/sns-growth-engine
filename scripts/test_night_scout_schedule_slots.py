#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    text = (ROOT / ".github/workflows/autonomous-growth-loop-night-scout.yml").read_text(encoding="utf-8")
    expected = ['cron: "45 4 * * *"', 'cron: "45 6 * * *"', 'cron: "45 8 * * *"', 'cron: "45 15 * * *"']
    media = (ROOT / ".github/workflows/media-growth-post-night-scout.yml").read_text(encoding="utf-8")
    ok = all(x in text for x in expected) and 'cron: "45 11 * * *"' in media and "The 21:00 slot is owned" in text
    print(f"  {'PASS' if ok else 'FAIL'} night_scout schedule slots")
    print(f"PASS: {1 if ok else 0} / FAIL: {0 if ok else 1}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
