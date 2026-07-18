#!/usr/bin/env python3
"""A successful canonical fallback must be visible as a posted autonomous run."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from run_autonomous_loop import summarize_autonomous_results  # noqa: E402


def main() -> int:
    result = summarize_autonomous_results("night_scout", "apply", [{
        "cmd": "scripts/run_slot_text_fallback.py --apply --confirm-slot-fallback",
        "returncode": 0,
        "payload": {"status": "POSTED"},
        "stdout_tail": '{"status": "POSTED"}',
    }])
    ok = (
        result["posted_count"] == 1
        and result["processed_count"] == 1
        and result["apply_status"] == "POSTED"
        and result["no_post_reason"] == ""
    )
    print(f"  {'PASS' if ok else 'FAIL'} slot fallback contributes to posted health summary")
    print(f"PASS: {1 if ok else 0} / FAIL: {0 if ok else 1}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
