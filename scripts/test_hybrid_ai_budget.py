#!/usr/bin/env python3
from __future__ import annotations

import tempfile
from pathlib import Path

import hybrid_ai_budget as budget


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        budget.STATE_PATH = Path(tmp) / "budget.json"
        budget.EXECUTION_MAX_REQUESTS = 20
        budget.DAILY_MAX_REQUESTS = 4
        budget.MONTHLY_MAX_REQUESTS = 6
        first = budget.reserve(1, {"test": "first"})
        assert first["daily_used"] == 1
        assert first["monthly_used"] == 1
        second = budget.reserve(3)
        assert second["daily_used"] == 4
        allowed, reasons, _ = budget.check_capacity(1)
        assert allowed is False
        assert "daily_limit_exceeded" in reasons
        state = budget.load_state()
        assert state.daily_used == 4
        assert state.monthly_used == 4
        assert budget.show()["day_key"]
    print("PASS 5 tests")


if __name__ == "__main__":
    main()
