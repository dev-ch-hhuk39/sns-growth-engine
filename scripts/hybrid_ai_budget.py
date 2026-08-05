#!/usr/bin/env python3
"""Atomic request-budget guard for the Gemini hybrid gate."""
from __future__ import annotations

import argparse
import fcntl
import json
import os
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator
from zoneinfo import ZoneInfo

JST = ZoneInfo("Asia/Tokyo")
STATE_PATH = Path(os.environ.get("HYBRID_AI_BUDGET_STATE", ".runtime/hybrid_ai_budget.json"))
EXECUTION_MAX_REQUESTS = int(os.environ.get("HYBRID_AI_EXECUTION_MAX_REQUESTS", "20"))
DAILY_MAX_REQUESTS = int(os.environ.get("HYBRID_AI_DAILY_MAX_REQUESTS", "40"))
MONTHLY_MAX_REQUESTS = int(os.environ.get("HYBRID_AI_MONTHLY_MAX_REQUESTS", "1000"))


@dataclass
class BudgetState:
    day_key: str
    month_key: str
    daily_used: int
    monthly_used: int

    @classmethod
    def fresh(cls, now: datetime) -> "BudgetState":
        return cls(now.strftime("%Y-%m-%d"), now.strftime("%Y-%m"), 0, 0)


def now_jst() -> datetime:
    return datetime.now(JST)


def _lock_path() -> Path:
    return STATE_PATH.with_suffix(STATE_PATH.suffix + ".lock")


@contextmanager
def locked_state() -> Iterator[None]:
    lock_path = _lock_path()
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _load_unlocked(now: datetime) -> BudgetState:
    if not STATE_PATH.exists():
        return BudgetState.fresh(now)
    try:
        raw = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        state = BudgetState(
            day_key=str(raw["day_key"]),
            month_key=str(raw["month_key"]),
            daily_used=int(raw["daily_used"]),
            monthly_used=int(raw["monthly_used"]),
        )
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"hybrid_ai_budget_state_invalid:{exc}") from exc
    current_day = now.strftime("%Y-%m-%d")
    current_month = now.strftime("%Y-%m")
    if state.month_key != current_month:
        return BudgetState.fresh(now)
    if state.day_key != current_day:
        state.day_key = current_day
        state.daily_used = 0
    return state


def _save_unlocked(state: BudgetState) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE_PATH.with_suffix(STATE_PATH.suffix + ".tmp")
    tmp.write_text(json.dumps(asdict(state), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, STATE_PATH)


def load_state(now: datetime | None = None) -> BudgetState:
    current = now or now_jst()
    with locked_state():
        return _load_unlocked(current)


def check_capacity(request_count: int, state: BudgetState | None = None) -> tuple[bool, list[str], dict[str, int]]:
    if request_count < 0:
        raise ValueError("request_count must be >= 0")
    current = state or load_state()
    reasons: list[str] = []
    if request_count > EXECUTION_MAX_REQUESTS:
        reasons.append("execution_limit_exceeded")
    if current.daily_used + request_count > DAILY_MAX_REQUESTS:
        reasons.append("daily_limit_exceeded")
    if current.monthly_used + request_count > MONTHLY_MAX_REQUESTS:
        reasons.append("monthly_limit_exceeded")
    snapshot = {
        "execution_max_requests": EXECUTION_MAX_REQUESTS,
        "daily_max_requests": DAILY_MAX_REQUESTS,
        "monthly_max_requests": MONTHLY_MAX_REQUESTS,
        "request_count": request_count,
        "daily_used": current.daily_used,
        "monthly_used": current.monthly_used,
        "daily_remaining": max(0, DAILY_MAX_REQUESTS - current.daily_used),
        "monthly_remaining": max(0, MONTHLY_MAX_REQUESTS - current.monthly_used),
    }
    return not reasons, reasons, snapshot


def reserve(request_count: int = 1, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    if request_count <= 0:
        raise ValueError("request_count must be > 0")
    current_time = now_jst()
    with locked_state():
        state = _load_unlocked(current_time)
        allowed, reasons, snapshot = check_capacity(request_count, state)
        if not allowed:
            raise RuntimeError(
                "hybrid_ai_budget_blocked:"
                + json.dumps({"reasons": reasons, "snapshot": snapshot}, ensure_ascii=False, sort_keys=True)
            )
        state.daily_used += request_count
        state.monthly_used += request_count
        _save_unlocked(state)
    return {
        "request_count": request_count,
        "day_key": state.day_key,
        "month_key": state.month_key,
        "daily_used": state.daily_used,
        "monthly_used": state.monthly_used,
        "daily_remaining": max(0, DAILY_MAX_REQUESTS - state.daily_used),
        "monthly_remaining": max(0, MONTHLY_MAX_REQUESTS - state.monthly_used),
        "metadata": metadata or {},
    }


def consume(request_count: int) -> dict[str, Any]:
    return reserve(request_count)


def show() -> dict[str, Any]:
    state = load_state()
    return {
        **asdict(state),
        "execution_max_requests": EXECUTION_MAX_REQUESTS,
        "daily_max_requests": DAILY_MAX_REQUESTS,
        "monthly_max_requests": MONTHLY_MAX_REQUESTS,
        "daily_remaining": max(0, DAILY_MAX_REQUESTS - state.daily_used),
        "monthly_remaining": max(0, MONTHLY_MAX_REQUESTS - state.monthly_used),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("show")
    check_parser = sub.add_parser("check")
    check_parser.add_argument("request_count", type=int)
    reserve_parser = sub.add_parser("reserve")
    reserve_parser.add_argument("request_count", type=int)
    args = parser.parse_args()
    if args.command == "show":
        output = show()
    elif args.command == "check":
        allowed, reasons, snapshot = check_capacity(args.request_count)
        output = {"allowed": allowed, "reasons": reasons, "snapshot": snapshot}
    else:
        output = reserve(args.request_count)
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
