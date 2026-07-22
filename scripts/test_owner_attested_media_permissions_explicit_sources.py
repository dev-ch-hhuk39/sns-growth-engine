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
reference_only = module.eligible_sources({"src_ns_threads_user_chiishunin_s"})
checks = {
    "explicit approved sources selected": approved == {"src_lm_tt_user_001", "src_ns_yt_cand_001"},
    "reference-only Threads source excluded": reference_only == [],
    "apply demands explicit source IDs": "--apply requires at least one explicit --source-id" in (ROOT / "scripts" / "seed_owner_attested_media_permissions.py").read_text(encoding="utf-8"),
    "approved rights are required": "APPROVABLE_RIGHTS" in (ROOT / "scripts" / "seed_owner_attested_media_permissions.py").read_text(encoding="utf-8"),
}
for name, ok in checks.items():
    print(f"{'PASS' if ok else 'FAIL'} {name}")
raise SystemExit(0 if all(checks.values()) else 1)
