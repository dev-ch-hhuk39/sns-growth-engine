#!/usr/bin/env python3
"""Permission seeding must not mass-upgrade reference-only sources."""
from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("permission_seed", ROOT / "scripts" / "seed_owner_attested_media_permissions.py")
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

approved = {item["source_id"] for item in module.eligible_sources({"src_lm_tt_user_001", "src_ns_yt_cand_001"})}
registered_threads = module.eligible_sources({"src_ns_threads_user_chiishunin_s"})
threads_permission = module.permission_row(registered_threads[0], "2026-08-24T00:00:00+00:00")
checks = {
    "explicit approved sources selected": approved == {"src_lm_tt_user_001", "src_ns_yt_cand_001"},
    "registered owner-approved Threads source selected": len(registered_threads) == 1,
    "registered Threads clip grant preserves canonical provenance": (
        threads_permission["allow_original_repost"] == "true"
        and threads_permission["allow_cut"] == "true"
        and threads_permission["evidence_reference"] == registered_threads[0]["permission_evidence_reference"]
        and registered_threads[0]["original_author_match_required"] is True
    ),
    "apply demands explicit source IDs": "--apply requires at least one explicit --source-id" in (ROOT / "scripts" / "seed_owner_attested_media_permissions.py").read_text(encoding="utf-8"),
    "approved rights are required": "APPROVABLE_RIGHTS" in (ROOT / "scripts" / "seed_owner_attested_media_permissions.py").read_text(encoding="utf-8"),
}
for name, ok in checks.items():
    print(f"{'PASS' if ok else 'FAIL'} {name}")
raise SystemExit(0 if all(checks.values()) else 1)
