#!/usr/bin/env python3
"""Static contract checks after the guarded Mac worker patch is applied."""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKER = ROOT / "scripts/process_threads_queue.py"


def main() -> int:
    src = WORKER.read_text(encoding="utf-8")
    ast.parse(src)
    pairs = [
        ("preflight before Sheets PROCESSING mutation",
         "p0_once = None", 'locked = update_row(client, "queue"'),
        ("durable claim before real provider call",
         "p0_once.claim(", "    result = publisher.publish("),
        ("provider ACK before result persistence",
         "p0_once.provider_accepted(", "if not result.success:"),
        ("two readbacks before success",
         "p0_once.verify_posted(", 'slot_warning = ""'),
    ]
    assert src.count("SNS_P0_ONCE_BARRIER") == 4, "one-use guard missing or duplicated"
    assert "SNS_P0_ONCE_GATE_ENABLED" in src, "explicit off-by-default flag missing"
    assert "P0_ONCE_GATE_NOT_ACTIVATED" in src, "unprotected real write not refused"
    assert "P0_RELEASE_OWNER_CONSENT_OR_LIVE_PROOF_INVALID" in src
    assert src.index("verify_release(") < src.index('locked = update_row(client, "queue"')
    assert src.index("P0_ONCE_GATE_NOT_ACTIVATED") < src.index('locked = update_row(client, "queue"')
    assert src.count("    result = publisher.publish(") == 1, "real call count changed"
    assert src.count('    if not confirm_real_post:') == 1, "real-post opt-in changed"
    assert "ALLOW_REAL_THREADS_POST" in src and "PUBLISH_ENABLED" in src
    for title, left, right in pairs:
        assert src.count(left) == 1 and src.count(right) >= 1 and src.index(left) < src.index(right), title
        print(f"PASS: {title}")
    print("P0_ONCE_WORKER_CONTRACT_PASS: opt-in only, no network calls")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
