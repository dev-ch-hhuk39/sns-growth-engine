#!/usr/bin/env python3
"""Owner decision must remain exact, handle-scoped, and non-inheritable."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "src")]

from media.permission_ledger import evaluate_permission  # noqa: E402
from seed_owner_attested_media_permissions import (  # noqa: E402
    DECISION_REQUIRED_FLAGS,
    decision_sources,
    load_owner_decision,
    permission_row,
)

decision = load_owner_decision(ROOT / "config/owner_source_permissions_20260811.json")
sources = decision_sources(decision)
rows = [permission_row(source, "2026-08-11T01:23:45+00:00", decision) for source in sources]
counts: dict[tuple[str, str], int] = {}
for source in sources:
    key = (source["account_id"], source["platform"])
    counts[key] = counts.get(key, 0) + 1

sample = next(row for row in rows if row["source_id"] == "src_lm_x_cand_001")
checks = {
    "all 24 explicit identities selected": len(sources) == 24,
    "night X count": counts.get(("night_scout", "x")) == 10,
    "night Threads count": counts.get(("night_scout", "threads")) == 8,
    "night TikTok absent": counts.get(("night_scout", "tiktok"), 0) == 0,
    "liver X count": counts.get(("liver_manager", "x")) == 2,
    "liver Threads count": counts.get(("liver_manager", "threads")) == 1,
    "liver TikTok count": counts.get(("liver_manager", "tiktok")) == 3,
    "all operation flags explicit": all(sample[key] == "true" for key in DECISION_REQUIRED_FLAGS),
    "handle scoped": sample["source_handle"] == "@meg_lsm",
    "account scoped": sample["allowed_accounts"] == "liver_manager",
    "Threads destination only": sample["allowed_platforms"] == "threads",
    "exact owner evidence": sample["evidence_reference"] == decision["evidence_reference"],
    "correct handle accepted": evaluate_permission(
        [sample],
        "src_lm_x_cand_001",
        account_id="liver_manager",
        source_handle="@meg_lsm",
        required_flags=DECISION_REQUIRED_FLAGS,
    )["allowed"],
    "third-party handle rejected": not evaluate_permission(
        [sample],
        "src_lm_x_cand_001",
        account_id="liver_manager",
        source_handle="@third_party",
        required_flags=DECISION_REQUIRED_FLAGS,
    )["allowed"],
    "inheritance explicitly prohibited": "third_party_repost_permission_inheritance" in decision["prohibited_uses"],
}
for name, ok in checks.items():
    print(f"{'PASS' if ok else 'FAIL'} {name}")
raise SystemExit(0 if all(checks.values()) else 1)
