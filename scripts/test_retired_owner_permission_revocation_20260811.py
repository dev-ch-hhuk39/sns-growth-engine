#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "src")]

from media.permission_ledger import evaluate_permission  # noqa: E402
from seed_owner_attested_media_permissions import (  # noqa: E402
    DECISION_REQUIRED_FLAGS,
    load_owner_decision,
    retired_decision_sources,
    revocation_row,
)

decision = load_owner_decision(ROOT / "config/owner_source_permissions_20260811.json")
retired = retired_decision_sources(decision)
rows = [revocation_row(source, "2026-08-11T08:00:00+00:00", decision) for source in retired]
checks = {
    "exactly three retired sources": {row["source_id"] for row in rows} == {"src_ns_x_cand_002", "src_ns_x_cand_006", "src_ns_x_owner_kyabataihendane"},
    "all append-only rows revoked": all(row["revoked"] == "true" and row["permission_status"] == "revoked" for row in rows),
    "all operation flags disabled": all(row[flag] == "false" for row in rows for flag in DECISION_REQUIRED_FLAGS),
    "effective permission denied": all(not evaluate_permission([row], row["source_id"], account_id="night_scout", source_handle=row["source_handle"], required_flags=DECISION_REQUIRED_FLAGS)["allowed"] for row in rows),
}
for name, ok in checks.items():
    print(f"{'PASS' if ok else 'FAIL'} {name}")
raise SystemExit(0 if all(checks.values()) else 1)
