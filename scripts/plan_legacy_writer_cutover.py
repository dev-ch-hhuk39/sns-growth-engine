#!/usr/bin/env python3
"""Standalone offline inventory and staged cutover planning for Sheets writers.

Classifies the committed AST baseline into migration workstreams without
granting publication, assigning authority, or touching Sheets/SQLite.
All routes remain NOT_MIGRATED until separate owner-approved operational
proof exists. A clean static inventory is not a migration release gate.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

from test_phase5b6h_legacy_sheets_mutation_inventory import (
    MANIFEST, ROOT, collect_inventory,
)

GROUPS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("P0_PUBLISH_AND_RESULT", (
        "scripts/process_threads_queue.py", "scripts/publish_queue.py",
        "scripts/recover_orphan_threads_post.py",
        "scripts/repair_posted_results_integrity.py",
        "scripts/collect_threads_metrics.py",
    )),
    ("P0_QUEUE_AND_APPROVAL", (
        "src/sheets_client.py", "src/queue_builder.py",
        "scripts/auto_approve_queue.py", "scripts/approve_queue.py",
        "scripts/apply_publication_review_decisions.py",
        "scripts/sync_publication_review.py",
        "scripts/sns_failclosed_unapproved_ready.py",
        "scripts/normalize_scheduled_media_caption.py",
        "scripts/promote_hybrid_approved_media.py",
        "scripts/prepare_beauty_review_candidates.py",
        "scripts/run_hybrid_ai_queue_gate.py",
        "scripts/normalize_unreviewed_slot_candidates.py",
        "scripts/archive_pre_activation_queue.py",
        "scripts/refill_threads_queue.py",
        "scripts/generate_next_queue_from_metrics.py",
        "src/generation/video_clip_generator.py",
    )),
    ("P1_SCHEMA_AND_RECOVERY", (
        "scripts/recover_production_sheets_threads_first.py",
        "scripts/reconcile_production_integrity.py",
        "scripts/apply_source_identity_repairs.py",
        "scripts/ensure_route_provenance_schema.py",
        "scripts/setup_sheets.py",
    )),
    ("P1_METRICS_AND_FEEDBACK", (
        "scripts/metrics_reservations.py",
        "scripts/process_threads_metric_jobs.py",
        "scripts/run_growth_attribution_cycle.py",
        "scripts/content_slot_runs.py",
        "scripts/evergreen_inventory.py",
        "scripts/run_pdca_cycle.py",
    )),
)
# Every unclassified legacy mutator is still included as P2, not ignored.
DEFAULT_GROUP = "P2_UPSTREAM_AND_OTHER"
PRIORITY = {"P0": 0, "P1": 1, "P2": 2}


class CutoverPlanBlocked(ValueError):
    """Only static reason codes, never source/provider payloads."""


def build_plan(
    *, baseline: dict[str, dict[str, int]] | None = None,
    current: dict[str, dict[str, int]] | None = None,
) -> dict[str, Any]:
    if baseline is None:
        try:
            baseline = json.loads(MANIFEST.read_text(encoding="utf-8"))["routes"]
        except (OSError, ValueError, KeyError, TypeError):
            raise CutoverPlanBlocked("SHEETS_WRITER_BASELINE_UNAVAILABLE") from None
    if current is None:
        try:
            current = collect_inventory()
        except Exception:
            raise CutoverPlanBlocked("SHEETS_WRITER_AST_SCAN_UNAVAILABLE") from None
    if (not isinstance(baseline, dict) or not isinstance(current, dict)
            or baseline != current):
        raise CutoverPlanBlocked("SHEETS_WRITER_BASELINE_DRIFT")
    groups = {
        filepath: name
        for name, files in GROUPS
        for filepath in files
    }
    if len(groups) != sum(len(paths) for _, paths in GROUPS):
        raise CutoverPlanBlocked("SHEETS_WRITER_DUPLICATE_CLASSIFICATION")
    sites = []
    for filename, calls in baseline.items():
        if (not filename.startswith(("src/", "scripts/"))
                or not filename.endswith(".py")
                or not isinstance(calls, dict)):
            raise CutoverPlanBlocked("SHEETS_WRITER_INVENTORY_INVALID")
        group = groups.get(filename, DEFAULT_GROUP)
        for method, count in calls.items():
            if not isinstance(method, str) or type(count) is not int or count < 1:
                raise CutoverPlanBlocked("SHEETS_WRITER_COUNT_INVALID")
            identity = hashlib.sha256(
                f"{filename}:{method}".encode("utf-8"),
            ).hexdigest()[:16]
            sites.append({
                "site_hash": identity, "file": filename, "method": method,
                "calls": count, "workstream": group,
                "migration_state": "NOT_MIGRATED",
                "external_side_effect_approved": False,
                "cutover_authorized": False,
            })
    sites.sort(key=lambda item: (
        PRIORITY[item["workstream"][:2]],
        item["file"], item["method"],
    ))
    totals = Counter()
    for row in sites:
        totals[row["workstream"]] += row["calls"]
    return {
        "schema": "sns_legacy_writer_cutover_plan_v1",
        "status": "CUTOVER_BLOCKED",
        "release_approval": False,
        "operational_source_selected": False,
        "operational_writes_executed": 0,
        "files": len(baseline),
        "mutation_sites": sum(v for methods in baseline.values() for v in methods.values()),
        "not_migrated_sites": sum(x["calls"] for x in sites),
        "workstream_counts": dict(sorted(totals.items())),
        "remaining_release_blockers": [
            "OWNER_AUTHORITY_SELECTION_MISSING",
            "PROVIDER_IDENTITY_AND_ACL_NOT_ATTESTED",
            "MUTATOR_CALLEE_REVIEW_NOT_COMPLETED",
            "ACTUAL_WRITER_DISABLEMENT_NOT_VERIFIED",
            "BACKUP_RESTORE_AND_ROLLBACK_NOT_TESTED",
            "CROSS_PROCESS_CAS_NOT_PROVEN",
            "REAL_CANARY_AND_METRIC_EVIDENCE_MISSING",
        ],
        "routes": sites,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path,
                        help="Optional absolute path outside the Git worktree")
    args = parser.parse_args()
    try:
        result = build_plan()
    except CutoverPlanBlocked as error:
        result = {"schema": "sns_legacy_writer_cutover_plan_v1",
                  "status": "CUTOVER_BLOCKED", "release_approval": False,
                  "reason": str(error)}
    output = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        target = args.output.resolve()
        if (not args.output.is_absolute()
                or target == ROOT or ROOT in target.parents):
            parser.error("REPORT_MUST_BE_EXTERNAL_ABSOLUTE_PATH")
        args.output.write_text(output, encoding="utf-8")
    print(output, end="")
    return 2  # never treat an inventory as a cutover permit


if __name__ == "__main__":
    raise SystemExit(main())
