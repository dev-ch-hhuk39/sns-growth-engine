#!/usr/bin/env python3
"""Read-only final blocker report from an existing minimal queue manifest.

No live reads, credentials, DBs, rehearsal claims, or apply/output-file mode.
Offline metadata cannot attest writer custody, identity, rights or aftercare;
even clean metadata never constitutes operational readiness or authorization.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from audit_queue_authority_cutover import load_offline_snapshot, legacy_writer_snapshot
from p0_release_readiness import HARD_BLOCKERS
from p0_snapshot_cutover_preflight import inspect


def build_report(snapshot_path: Path | None, *, now: datetime) -> dict:
    result = {
        "schema": "sns_final_operational_readiness_offline_v1",
        "status": "CUTOVER_BLOCKED",
        "production_ready": False,
        "publish_authorized": False,
        "production_cutover_authorized": False,
        "sheets_write_authorized": False,
        "operational_sqlite_write_authorized": False,
        "source_provenance": "UNATTESTED_OFFLINE_METADATA_ONLY",
        "writer_inventory_status": "NOT_VERIFIED",
        "legacy_mutation_sites": None,
        "snapshot_status": "NOT_VERIFIED",
        "queue_rows_count": None,
        "posted_rows_count": None,
        "findings": [],
        "mandatory_production_blockers": sorted(set(HARD_BLOCKERS) | {
            "ACCOUNT_PROVIDER_IDENTITY_NOT_ATTESTED",
            "BEAUTY_EXCLUDED_AND_MEDIA_RIGHTS_NOT_ATTESTED",
        }),
    }
    try:
        inventory = legacy_writer_snapshot()
        result["legacy_mutation_sites"] = inventory["sites"]
        result["writer_inventory_status"] = "BASELINE_MATCH_ONLY_NOT_EXCLUSIVITY"
    except Exception:
        result["findings"].append("LEGACY_WRITER_INVENTORY_UNVERIFIABLE")
    if snapshot_path is None:
        result["findings"].append("OFFLINE_SNAPSHOT_MISSING")
        return result
    try:
        # Refuse symlinks rather than implicitly following another data source.
        if snapshot_path.is_symlink():
            raise ValueError
        snapshot = load_offline_snapshot(snapshot_path)
        if result["legacy_mutation_sites"] is None:
            result["findings"].append("SNAPSHOT_NOT_EVALUATED_WITHOUT_WRITER_INVENTORY")
            return result
        checked = inspect(snapshot, as_of=now,
                          legacy_writer_sites=result["legacy_mutation_sites"]).report
        # Only locally computed codes/counts are serialized, never input claims,
        # exception messages, paths, identities, body text or provider IDs.
        result["queue_rows_count"] = checked["queue_rows_count"]
        result["posted_rows_count"] = checked["posted_rows_count"]
        result["findings"].extend(sorted({x["code"] for x in checked["findings"]}))
        result["snapshot_status"] = (
            "BLOCKED" if checked["findings"] else "CHECKED_UNATTESTED_METADATA_ONLY"
        )
    except Exception:
        result["findings"].append("OFFLINE_SNAPSHOT_UNVERIFIABLE")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path,
                        help="Existing minimal metadata manifest; no text, URLs or secrets")
    args = parser.parse_args()
    print(json.dumps(build_report(args.snapshot, now=datetime.now(timezone.utc)), indent=2))
    return 2  # A diagnostic report is never a release or posting permit.


if __name__ == "__main__":
    raise SystemExit(main())
