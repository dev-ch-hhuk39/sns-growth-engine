#!/usr/bin/env python3
"""A stale empty fallback cannot starve a newly generated READY candidate."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import process_threads_queue as worker  # noqa: E402


class FakeWorksheet:
    def get_all_records(self):
        return [
            {
                "queue_id": "legacy-empty",
                "account_id": "night_scout",
                "platform": "threads",
                "priority": "1",
                "status": "READY",
                "generation_mode": "slot_fallback_original_text",
                "public_post_text": "",
            },
            {
                "queue_id": "fresh-safe",
                "account_id": "night_scout",
                "platform": "threads",
                "priority": "50",
                "status": "READY",
                "generation_mode": "original_text",
                "public_post_text": "夜職で続けやすい店は、条件より相談しやすさを見た方がいい。\n\n迷った時に一人で抱え込まないことが、長く働くための準備になる。",
            },
        ]


class FakeClient:
    def _ws(self, _logical):
        return FakeWorksheet()


def main() -> int:
    selected = worker.select_candidates(FakeClient(), "night_scout", 1)
    ok = len(selected) == 1 and selected[0]["queue_id"] == "fresh-safe"
    print(f"  {'PASS' if ok else 'FAIL'} fresh public candidate ranks before legacy empty fallback")
    print(f"PASS: {1 if ok else 0} / FAIL: {0 if ok else 1}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
