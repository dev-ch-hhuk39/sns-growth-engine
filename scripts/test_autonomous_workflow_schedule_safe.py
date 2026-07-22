#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    manual = (ROOT / ".github/workflows/autonomous-growth-loop.yml").read_text(encoding="utf-8")
    texts = [
        (ROOT / ".github/workflows/autonomous-growth-loop-night-scout.yml").read_text(encoding="utf-8"),
        (ROOT / ".github/workflows/autonomous-growth-loop-liver-manager.yml").read_text(encoding="utf-8"),
    ]
    checks = [
        ("manual workflow has no schedule", "schedule:" not in manual),
        ("account schedules enabled", all("schedule:" in text for text in texts)),
        ("confirm still required", all("confirm_autonomous" in text for text in texts)),
        ("schedule can apply", all("github.event_name == 'schedule' || github.event.inputs.confirm_autonomous == 'true'" in text for text in texts)),
        ("kill switch checked", all("kill_switch" in text for text in texts)),
        ("workflow default false", all('PUBLISH_ENABLED: "false"' in text for text in texts)),
        ("no idle delay", all("time.sleep" not in text and "random.randint" not in text for text in texts)),
    ]
    failed = [n for n, ok in checks if not ok]
    for n, ok in checks:
        print(f"  {'PASS' if ok else 'FAIL'} {n}")
    print(f"PASS: {len(checks)-len(failed)} / FAIL: {len(failed)}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
