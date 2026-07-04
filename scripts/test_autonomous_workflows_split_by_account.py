#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    night = ROOT / ".github/workflows/autonomous-growth-loop-night-scout.yml"
    liver = ROOT / ".github/workflows/autonomous-growth-loop-liver-manager.yml"
    manual = (ROOT / ".github/workflows/autonomous-growth-loop.yml").read_text(encoding="utf-8")
    checks = [
        ("night workflow exists", night.exists()),
        ("liver workflow exists", liver.exists()),
        ("manual workflow has no schedule", "schedule:" not in manual),
        ("night account fixed", 'ACCOUNT_ID: "night_scout"' in night.read_text(encoding="utf-8")),
        ("liver account fixed", 'ACCOUNT_ID: "liver_manager"' in liver.read_text(encoding="utf-8")),
    ]
    failed = [n for n, ok in checks if not ok]
    for n, ok in checks:
        print(f"  {'PASS' if ok else 'FAIL'} {n}")
    print(f"PASS: {len(checks)-len(failed)} / FAIL: {len(failed)}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
