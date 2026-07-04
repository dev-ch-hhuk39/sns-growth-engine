#!/usr/bin/env python3
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    cfg = json.loads((ROOT / "config/autonomous_mode.json").read_text(encoding="utf-8"))
    rules = json.loads((ROOT / "config/auto_approval_rules.json").read_text(encoding="utf-8"))["defaults"]
    ok = cfg["daily_post_cap_per_account"] == 5 and cfg["daily_ready_cap_per_account"] == 8 and cfg["max_posts_per_run"] == 1 and cfg["cooldown_minutes"] == 90 and rules["daily_post_cap"] == 5
    print(f"  {'PASS' if ok else 'FAIL'} daily cap allows five posts per account")
    print(f"PASS: {1 if ok else 0} / FAIL: {0 if ok else 1}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
