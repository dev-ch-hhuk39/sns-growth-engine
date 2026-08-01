#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

sys.path.insert(
    0,
    str(ROOT / "scripts"),
)

from generate_threads_ideas_from_references import (
    FALLBACK_ATTEMPTS_PER_SLOT,
    build_fallback_generation_rows,
)


assert FALLBACK_ATTEMPTS_PER_SLOT == 64

for schedule_date_jst in (
    "20260801",
    "20260831",
):
    for account_id in (
        "night_scout",
        "liver_manager",
    ):
        rows = build_fallback_generation_rows(
            account_id=account_id,
            top_n=5,
            schedule_date_jst=(
                schedule_date_jst
            ),
        )

        drafts = list(
            rows.get(
                "drafts",
                [],
            )
        )

        queue = list(
            rows.get(
                "queue",
                [],
            )
        )

        texts = [
            str(
                row.get(
                    "body_md",
                    "",
                )
            )
            for row in drafts
        ]

        assert len(drafts) == 5, (
            schedule_date_jst,
            account_id,
            len(drafts),
        )

        assert len(queue) == 5, (
            schedule_date_jst,
            account_id,
            len(queue),
        )

        assert len(set(texts)) == 5, (
            schedule_date_jst,
            account_id,
            texts,
        )

        assert all(
            row.get(
                "validator_status"
            )
            == "PASS"
            for row in queue
        )

        assert all(
            row.get(
                "batch_diversity_status"
            )
            == "PASS"
            for row in queue
        )

print(
    "PASS "
    "test_fallback_retry_budget_contract.py"
)
