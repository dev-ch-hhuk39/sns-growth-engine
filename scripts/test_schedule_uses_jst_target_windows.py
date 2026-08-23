#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    night = (ROOT / ".github/workflows/autonomous-growth-loop-night-scout.yml").read_text(encoding="utf-8")
    liver = (ROOT / ".github/workflows/autonomous-growth-loop-liver-manager.yml").read_text(encoding="utf-8")
    guard = (ROOT / "scripts/scheduled_execution_guard.py").read_text(encoding="utf-8")
    ok = (
        all(cron in night for cron in ['cron: "45 4 * * *"', 'cron: "45 6 * * *"', 'cron: "45 15 * * *"'])
        and all(cron in liver for cron in ['cron: "45 0 * * *"', 'cron: "45 3 * * *"', 'cron: "45 11 * * *"'])
        and "Early runtime preflight" in night
        and "Early runtime preflight" in liver
        and "scheduled_window_decision" in night + liver
        and 'MAX_SCHEDULE_DELAY_MINUTES = int(os.environ.get("MAX_SCHEDULE_DELAY_MINUTES", "15"))' in guard
        and "time.sleep" not in night + liver
    )
    print(f"  {'PASS' if ok else 'FAIL'} JST cron slots are canonical and delayed publication is bounded")
    print(f"PASS: {1 if ok else 0} / FAIL: {0 if ok else 1}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
