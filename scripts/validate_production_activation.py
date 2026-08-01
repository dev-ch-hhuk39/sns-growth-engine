#!/usr/bin/env python3
"""Fail-closed gate for enabling scheduled publishing after twelve canaries."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from final_production_contracts import activation_evidence

from activation_integrity import (
    ACTIVATION_DATASETS,
    evaluate_canary_integrity,
    load_activation_datasets,
)


def _live_rows(use_sheets: bool) -> tuple[list[dict[str, Any]], list[dict[str, Any]], str]:
    if not use_sheets:
        return [], [], "use_sheets_required"
    try:
        sys.path.insert(0, str(ROOT / "src"))
        from config_loader import get_config
        from sheets_client import SheetsClient

        cfg = get_config()
        client = SheetsClient(cfg["sheet_id"], cfg["sa_dict"], dry_run=True)
        return (
            [dict(row) for row in client._ws("posted_results").get_all_records()],
            [dict(row) for row in client._ws("metrics_collection_jobs").get_all_records()],
            "READ_OK",
        )
    except Exception as exc:
        # This is intentionally distinct from missing canary evidence.  The
        # initializer can repair it without touching existing operational rows.
        return (
            [],
            [],
            "SCHEMA_MISSING" if type(exc).__name__ == "WorksheetNotFound" else type(exc).__name__,
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)

    parser.add_argument(
        "--use-sheets",
        action="store_true",
    )

    parser.add_argument(
        "--input-json",
        type=Path,
        default=None,
    )

    args = parser.parse_args()

    if args.input_json:
        payload = json.loads(args.input_json.read_text(encoding="utf-8"))

        nested = payload.get(
            "datasets",
            {},
        )

        if not isinstance(
            nested,
            dict,
        ):
            nested = {}

        datasets = {
            logical: list(
                nested.get(
                    logical,
                    payload.get(
                        logical,
                        [],
                    ),
                )
                or []
            )
            for logical in ACTIVATION_DATASETS
        }

        source = "INPUT_JSON"

    else:
        datasets, source = load_activation_datasets(args.use_sheets)

    integrity = evaluate_canary_integrity(datasets)

    report = activation_evidence(
        datasets["posted_results"],
        datasets["metrics_collection_jobs"],
        canary_integrity=integrity,
    )

    report.update(
        {
            "evidence_source": source,
            "canary_source_integrity": (integrity),
            "inventory_candidate_count": (
                integrity.get(
                    "candidate_count",
                    0,
                )
            ),
            "scheduled_publish_enabled": (False),
            "production_publish_activation_approved": (False),
            "would_mutate_config": False,
        }
    )

    print(
        json.dumps(
            report,
            ensure_ascii=False,
            indent=2,
        )
    )

    return 0 if report["status"] == "READY_FOR_ACTIVATION" else 1


if __name__ == "__main__":
    raise SystemExit(main())
