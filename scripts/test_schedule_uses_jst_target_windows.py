#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    night = (ROOT / ".github/workflows/autonomous-growth-loop-night-scout.yml").read_text(encoding="utf-8")
    liver = (ROOT / ".github/workflows/autonomous-growth-loop-liver-manager.yml").read_text(encoding="utf-8")
    ok = (
        "Jobs start just after the target" in night
        and "Jobs start just after the target" in liver
        and "Diagnose schedule delay" in night
        and "Diagnose schedule delay" in liver
        and "steps.schedule_window.outputs.in_window" not in night + liver
        and "time.sleep" not in night + liver
    )
    print(f"  {'PASS' if ok else 'FAIL'} JST cron slots are canonical and delayed events remain dispatchable")
    print(f"PASS: {1 if ok else 0} / FAIL: {0 if ok else 1}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
