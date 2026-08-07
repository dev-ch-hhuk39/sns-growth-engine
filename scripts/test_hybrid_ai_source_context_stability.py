#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src"), str(ROOT / "scripts")]

from hybrid_ai_source_context import build_source_context, hybrid_ai_source_context_hash


def main() -> None:
    queue = {
        "queue_id": "q_text_stability",
        "account_id": "night_scout",
        "target_account_id": "night_scout",
        "platform": "threads",
        "generation_mode": "original_text",
        "content_type": "original_text",
        "public_post_text": "Text candidate for context stability.",
        "internal_analysis": "first private diagnostic note",
    }
    first = build_source_context(object(), queue)
    changed_private_note = build_source_context(
        object(),
        {**queue, "internal_analysis": "different private diagnostic note"},
    )
    assert first["source_text"] == ""
    assert changed_private_note["source_text"] == ""
    assert hybrid_ai_source_context_hash(first) == hybrid_ai_source_context_hash(changed_private_note)

    missing = {**first, "permission_evidence_status": "MISSING"}
    approved = {**first, "permission_evidence_status": "APPROVED"}
    assert hybrid_ai_source_context_hash(missing) != hybrid_ai_source_context_hash(approved)
    print("PASS test_hybrid_ai_source_context_stability.py")


if __name__ == "__main__":
    main()
