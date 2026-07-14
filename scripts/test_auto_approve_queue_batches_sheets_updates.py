#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("auto_approve_queue", ROOT / "scripts" / "auto_approve_queue.py")
mod = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(mod)


class FakeClient:
    def __init__(self) -> None:
        self.bulk_calls: list[list[tuple[str, dict]]] = []
        self.single_calls: list[tuple[str, dict]] = []
        self.logs: list[dict] = []

    def bulk_update_queue_items(self, updates: list[tuple[str, dict]]) -> int:
        self.bulk_calls.append(updates)
        return len(updates)

    def update_queue_item(self, queue_id: str, **fields: object) -> None:
        self.single_calls.append((queue_id, fields))

    def log(self, **fields: object) -> None:
        self.logs.append(fields)


def main() -> int:
    client = FakeClient()
    plan = {"results": [
        {"status": "APPROVABLE", "queue_id": "q-safe", "account_id": "night_scout", "quality_score": 90, "safety_score": 100, "risk_score": 0, "score_total": 190},
        {"status": "REJECTED", "queue_id": "q-rejected", "account_id": "night_scout", "reasons": ["quality_score_below_threshold"]},
    ]}
    result = mod.apply_ready(client, plan)
    updates = dict(client.bulk_calls[0]) if client.bulk_calls else {}
    checks = [
        ("uses one bulk queue update", len(client.bulk_calls) == 1),
        ("does not fall back to per-row updates", not client.single_calls),
        ("includes ready and rejected state persistence", set(updates) == {"q-safe", "q-rejected"}),
        ("only safe item is promoted", result["updated_queue_ids"] == ["q-safe"] and updates["q-safe"]["status"] == "READY"),
        ("rejected item is not promoted", "status" not in updates["q-rejected"]),
    ]
    failed = [name for name, ok in checks if not ok]
    for name, ok in checks:
        print(f"  {'PASS' if ok else 'FAIL'} {name}")
    print(f"PASS: {len(checks) - len(failed)} / FAIL: {len(failed)}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
