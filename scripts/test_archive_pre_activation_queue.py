#!/usr/bin/env python3
from __future__ import annotations

from archive_pre_activation_queue import build_plan


def main() -> int:
    rows = [
        {"queue_id": "q1", "account_id": "night_scout", "status": "READY"},
        {"queue_id": "q2", "account_id": "liver_manager", "status": "WAITING_REVIEW"},
        {"queue_id": "q3", "account_id": "night_scout", "status": "POSTED"},
        {
            "queue_id": "q4",
            "account_id": "night_scout",
            "status": "READY",
            "excluded_from_activation": "true",
        },
    ]
    result = build_plan(rows)
    assert result["archive_count"] == 2
    assert result["by_account"] == {"liver_manager": 1, "night_scout": 1}
    assert result["would_post"] is False
    print("PASS test_archive_pre_activation_queue.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
