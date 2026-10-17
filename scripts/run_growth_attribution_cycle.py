#!/usr/bin/env python3
"""Explain measured post outcomes and update bounded generation strategy state.

The cycle is read-only by default. Apply writes only attribution evidence and
bounded strategy rows. It never posts, changes queue status, or rewrites prompts.
"""
from __future__ import annotations

import argparse
import json
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from learning.feature_attribution import build_growth_cycle  # noqa: E402
from accounts.managed_accounts import account_choices  # noqa: E402


def _read_tab(client: Any, logical: str) -> tuple[list[dict[str, Any]], str]:
    try:
        return [dict(row) for row in client._ws(logical).get_all_records()], ""
    except Exception as exc:
        # An unavailable evidence source must not masquerade as an empty
        # dataset: that could turn an operational failure into harmless NO_DATA.
        return [], f"{logical}_READ_FAILED:{type(exc).__name__}"


class AttributionWriteBlocked(RuntimeError):
    """A sanitized write failure; ambiguous external results are never retried."""


_SHEET_NUMERIC_FIELDS = {
    "post_attributions": frozenset({
        "window_hours", "performance_score", "account_baseline_score",
        "delta_vs_baseline", "confidence",
    }),
    "strategy_state": frozenset({
        "sample_count", "account_sample_count", "mean_performance_score",
        "delta_vs_account", "confidence", "allocation_weight", "exploration_floor",
    }),
}


def _same_sheet_value(logical: str, header: str, observed: Any, expected: Any) -> bool:
    """Compare only declared numeric columns by numeric value.

    gspread get_all_records numericises whole-number cells to int, even when
    the RAW upsert specified 1.0. Identity, account and all JSON/text fields
    retain strict string equality so this cannot mask a mismatched record.
    """
    if header in _SHEET_NUMERIC_FIELDS.get(logical, ()):
        if not isinstance(observed, bool) and not isinstance(expected, bool):
            try:
                left = Decimal(str(observed))
                right = Decimal(str(expected))
                if left.is_finite() and right.is_finite():
                    return left == right
            except (InvalidOperation, ValueError):
                pass
    return str(observed) == str(expected)


_PUBLIC_REPORT_FIELDS = frozenset({
    "status", "account_id", "observation_count", "attribution_count",
    "strategy_row_count", "active_strategy_count", "would_write", "would_post",
    "would_rewrite_prompts", "readback_verified", "reason",
    "external_write_outcome_uncertain", "external_write_may_have_occurred",
    "requires_readonly_reconciliation",
})


def public_growth_cycle_report(result: dict[str, Any]) -> dict[str, Any]:
    """Return only non-identifying execution metadata for CI and operator logs.

    Never emit individual post IDs, source text, per-post metrics, strategy
    evidence, or free-form provider responses to hosted CI logs.
    """
    return {key: value for key, value in result.items()
            if key in _PUBLIC_REPORT_FIELDS
            and isinstance(value, (str, int, bool, float, type(None)))}


def _upsert_rows(
    client: Any, logical: str, key: str, rows: list[dict[str, Any]],
    *, account_id: str, max_changes: int,
) -> dict[str, int | bool]:
    """Strict, bounded RAW-value upsert with a read-after-write confirmation.

    The caller holds the account+Sheets lock and owns approval. A Google
    write is not atomic with the local state or with the second tab: any
    provider error/quota/partial write becomes an unknown outcome, never
    an automatic retry. Refuse unexpected tab schema, key collisions,
    cross-account rows, and formula interpretation.
    """
    from gspread.utils import rowcol_to_a1
    from sheets_client import TAB_DEFINITIONS

    if not 1 <= max_changes <= 500 or logical not in (
        "post_attributions", "strategy_state",
    ) or key not in ("attribution_id", "strategy_id"):
        raise AttributionWriteBlocked("attribution_write_scope_invalid")
    try:
        # Do not auto-create or silently extend production tabs here.
        ws = client._ws(logical)
        headers = ws.row_values(1)
        existing_records = ws.get_all_records()
    except Exception:
        raise AttributionWriteBlocked("attribution_output_tab_unavailable") from None
    if (not headers or len(headers) != len(set(headers))
            or not set(TAB_DEFINITIONS[logical]).issubset(headers)
            or key not in headers or "account_id" not in headers):
        raise AttributionWriteBlocked("attribution_output_schema_unverified")
    if len(rows) > max_changes:
        raise AttributionWriteBlocked("attribution_write_budget_exceeded")
    existing: dict[str, tuple[int, dict[str, Any]]] = {}
    for index, source in enumerate(existing_records, start=2):
        row_id = str(source.get(key, ""))
        if not row_id:
            continue
        if row_id in existing:
            raise AttributionWriteBlocked("attribution_existing_duplicate_key")
        existing[row_id] = (index, dict(source))

    updates: list[dict[str, Any]] = []
    appends: list[list[Any]] = []
    expected: dict[str, dict[str, Any]] = {}
    skipped = 0
    seen: set[str] = set()
    for source in rows:
        identity = str(source.get(key, ""))
        if (not identity or identity in seen
                or str(source.get("account_id", "")) != account_id):
            raise AttributionWriteBlocked("attribution_account_or_key_invalid")
        seen.add(identity)
        merged = dict(source)
        if identity in existing:
            row_number, old = existing[identity]
            if str(old.get("account_id", "")) != account_id:
                raise AttributionWriteBlocked("attribution_existing_account_mismatch")
            merged = {**old, **merged}
            # A stable result/window ID must not be restamped on each rerun.
            if logical == "post_attributions" and old.get("created_at"):
                merged["created_at"] = old["created_at"]
            if logical == "strategy_state" and old.get("updated_at"):
                # Do not rewrite identical learning evidence solely because
                # this invocation sampled a later wall-clock timestamp.
                if all(
                    _same_sheet_value(logical, header, old.get(header, ""), merged.get(header, ""))
                    for header in headers if header != "updated_at"
                ):
                    merged["updated_at"] = old["updated_at"]
            if all(_same_sheet_value(logical, header, old.get(header, ""), merged.get(header, "")) for header in headers):
                skipped += 1
                continue
            updates.append({
                "range": (
                    f"{rowcol_to_a1(row_number, 1)}:"
                    f"{rowcol_to_a1(row_number, len(headers))}"
                ),
                "values": [[merged.get(header, "") for header in headers]],
            })
        else:
            appends.append([merged.get(header, "") for header in headers])
        expected[identity] = merged

    if len(updates) + len(appends) > max_changes:
        raise AttributionWriteBlocked("attribution_write_budget_exceeded")
    if not expected:
        return {"created": 0, "updated": 0, "skipped": skipped, "readback_verified": True}
    try:
        # RAW ensures untrusted descriptions beginning '=' are not formulas.
        if updates:
            ws.batch_update(updates, value_input_option="RAW")
        if appends:
            ws.append_rows(appends, value_input_option="RAW")
        # One readback after both writes; verify exactly one identical row.
        verified = ws.get_all_records()
        found: dict[str, list[dict[str, Any]]] = {}
        for row in verified:
            row_id = str(row.get(key, ""))
            if row_id in expected:
                found.setdefault(row_id, []).append(dict(row))
        for identity, wanted in expected.items():
            if len(found.get(identity, [])) != 1:
                raise AttributionWriteBlocked("attribution_readback_mismatch")
            observed = found[identity][0]
            if any(not _same_sheet_value(logical, header, observed.get(header, ""), wanted.get(header, "")) for header in headers):
                raise AttributionWriteBlocked("attribution_readback_mismatch")
    except Exception:
        # A partial success or lost acknowledgment MUST NOT trigger blind
        # re-append. Return an unknown outcome requiring read-only inspection.
        raise AttributionWriteBlocked("attribution_external_outcome_unknown") from None
    return {
        "created": len(appends), "updated": len(updates),
        "skipped": skipped, "readback_verified": True,
    }


def _load_input(path: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return list(data.get("posted_results", [])), list(data.get("metric_snapshots", []))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--account-id",
        default="all",
        choices=account_choices(include_all=True),
    )
    parser.add_argument("--input-json", help="Offline input containing posted_results and metric_snapshots")
    parser.add_argument("--use-sheets", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm-attribution", action="store_true")
    parser.add_argument(
        "--max-write-rows", type=int, default=120,
        help="Maximum combined attribution/strategy rows in one approved run (1..500)",
    )
    parser.add_argument("--output", default="")
    args = parser.parse_args()

    # Prevent constructing a write-capable Google Sheets client before
    # rejecting missing approval or an unsafe multi-account write.
    # Offline JSON input must never be treated as a production apply source.
    blocked_reason = ""
    if not 1 <= args.max_write_rows <= 500:
        blocked_reason = "attribution_write_budget_must_be_1_to_500"
    elif args.apply and args.dry_run:
        blocked_reason = "dry_run_and_apply_are_mutually_exclusive"
    elif args.input_json and args.use_sheets:
        blocked_reason = "choose_exactly_one_input_source"
    elif args.apply and not args.confirm_attribution:
        blocked_reason = "apply_requires_confirm_attribution"
    elif args.apply and args.account_id == "all":
        blocked_reason = "apply_requires_one_account"
    elif args.apply and (not args.use_sheets or args.input_json):
        blocked_reason = "apply_requires_live_sheets_source"
    if blocked_reason:
        print(json.dumps({
            "status": "BLOCKED", "reason": blocked_reason,
            "would_write": False, "would_post": False,
        }, ensure_ascii=False))
        return 1

    client = None
    if args.input_json:
        posted, snapshots = _load_input(args.input_json)
    elif args.use_sheets:
        from config_loader import get_config
        from sheets_client import SheetsClient
        cfg = get_config()
        client = SheetsClient(cfg["sheet_id"], cfg["sa_dict"], dry_run=not args.apply)
        posted, posted_error = _read_tab(client, "posted_results")
        snapshots, snapshots_error = _read_tab(client, "metric_snapshots")
        if posted_error or snapshots_error:
            result = {
                "status": "READ_FAILED",
                "reasons": [item for item in (posted_error, snapshots_error) if item],
                "would_write": False,
                "would_post": False,
            }
            if args.output:
                Path(args.output).parent.mkdir(parents=True, exist_ok=True)
                Path(args.output).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 1
    else:
        print(json.dumps({"status": "BLOCKED", "reason": "--input-json or --use-sheets is required"}, ensure_ascii=False))
        return 1

    result = build_growth_cycle(posted, snapshots, account_id=args.account_id)
    result["would_write"] = False
    result["would_post"] = False
    result["would_rewrite_prompts"] = False

    if args.apply:
        planned_rows = len(result["attributions"]) + len(result["strategy_state"])
        if result["observation_count"] < 1:
            result.update({
                "status": "NO_MEASURED_OBSERVATIONS", "would_write": False,
                "reason": "no_verified_metrics_for_account",
            })
        elif planned_rows > args.max_write_rows:
            result.update({
                "status": "BLOCKED", "would_write": False,
                "reason": "attribution_write_budget_exceeded",
                "planned_rows": planned_rows,
                "write_row_limit": args.max_write_rows,
            })
        else:
            try:
                # Never mutate the operational queue/posted_results tabs in a
                # measurement-only update. Only pre-provisioned reporting
                # evidence/strategy tabs may be changed with this approval.
                attribution_ops = _upsert_rows(
                    client, "post_attributions", "attribution_id",
                    result["attributions"], account_id=args.account_id,
                    max_changes=args.max_write_rows,
                )
                strategy_ops = _upsert_rows(
                    client, "strategy_state", "strategy_id",
                    result["strategy_state"], account_id=args.account_id,
                    max_changes=args.max_write_rows,
                )
            except AttributionWriteBlocked as exc:
                result.update({
                    "status": "OUTCOME_UNKNOWN_BLOCKED",
                    "reason": str(exc),
                    "would_write": False,
                    "external_write_outcome_uncertain": True,
                    "external_write_may_have_occurred": True,
                    "requires_readonly_reconciliation": True,
                })
            else:
                result.update({
                    "status": "APPLIED",
                    "would_write": bool(
                        attribution_ops["created"] or attribution_ops["updated"]
                        or strategy_ops["created"] or strategy_ops["updated"]
                    ),
                    "attribution_operations": attribution_ops,
                    "strategy_operations": strategy_ops,
                    "readback_verified": True,
                })

    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    # --output remains an explicit local file for detailed investigation.
    # Hosted workflow stdout must not expose provider IDs or per-post metrics.
    stdout_result = public_growth_cycle_report(result) if args.use_sheets else result
    print(json.dumps(stdout_result, ensure_ascii=False, indent=2))
    return 0 if result.get("status") in {"PLAN_ONLY", "APPLIED"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
