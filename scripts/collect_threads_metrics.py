#!/usr/bin/env python3
"""Collect Threads metrics safely.

Default mode is PLAN_ONLY. This collector never fabricates unknown values:
unknown metrics stay null, confirmed zero stays 0. Real writes require
--apply --confirm-metrics.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

METRIC_KEYS = ("views", "likes", "comments", "reposts", "quotes", "profile_clicks", "follows", "line_adds")
ALLOWED_ACCOUNTS = {"night_scout", "liver_manager"}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_metric(value: str | None) -> int | None:
    if value is None or str(value).strip() == "":
        return None
    return int(str(value).strip())


def build_snapshot(*, row: dict[str, Any], source: str, confidence: str, metrics: dict[str, int | None], memo: str) -> dict[str, Any]:
    known = {k: v for k, v in metrics.items() if v is not None}
    if len(known) == len(METRIC_KEYS):
        status = "MEASURED"
    elif known:
        status = "PARTIAL"
    elif source == "unavailable":
        status = "UNAVAILABLE"
    else:
        status = "PENDING"
    return {
        "snapshot_id": f"ms_{row.get('result_id', 'unknown')}_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}",
        "result_id": row.get("result_id", ""),
        "account_id": row.get("account_id", ""),
        "platform": row.get("platform", "threads"),
        "post_url": row.get("post_url", ""),
        "collected_at": now_iso(),
        "source": source,
        "confidence": confidence,
        "metrics_status": status,
        "memo": memo,
        **{k: metrics.get(k) for k in METRIC_KEYS},
    }


def collect_unavailable(row: dict[str, Any], source: str = "unavailable") -> dict[str, Any]:
    return build_snapshot(
        row=row,
        source=source,
        confidence="none",
        metrics={k: None for k in METRIC_KEYS},
        memo="Metrics collector could not obtain trusted values; unknowns left null.",
    )


def _headers(ws) -> list[str]:
    return ws.row_values(1)


def _append_row(client, logical: str, row: dict[str, Any]) -> bool:
    ws = client._ws(logical)
    headers = _headers(ws)
    if not headers:
        return False
    ws.append_row(["" if row.get(h) is None else str(row.get(h, "")) for h in headers], value_input_option="USER_ENTERED")
    return True


def _update_posted_result(client, result_id: str, snapshot: dict[str, Any]) -> None:
    ws = client._ws("posted_results")
    headers = _headers(ws)
    cell = ws.find(result_id, in_column=headers.index("result_id") + 1)
    if cell is None:
        raise KeyError(f"result_id={result_id!r} not found")
    for key in [*METRIC_KEYS, "metrics_status", "collected_at", "manual_memo"]:
        if key not in headers:
            continue
        if key == "manual_memo":
            value = snapshot.get("memo", "")
        elif key == "collected_at":
            value = snapshot.get("collected_at", "")
        else:
            value = snapshot.get(key, "")
        if value is not None:
            ws.update_cell(cell.row, headers.index(key) + 1, str(value))


def load_rows(use_sheets: bool, result_id: str | None, account_id: str) -> tuple[Any | None, list[dict[str, Any]]]:
    if not use_sheets:
        return None, []
    from config_loader import get_config
    from sheets_client import SheetsClient
    cfg = get_config()
    client = SheetsClient(cfg["sheet_id"], cfg["sa_dict"], dry_run=False)
    rows = [dict(r) for r in client._ws("posted_results").get_all_records()]
    filtered = []
    for row in rows:
        if result_id and str(row.get("result_id", "")) != result_id:
            continue
        if account_id != "all" and str(row.get("account_id", "")) != account_id:
            continue
        if str(row.get("platform", "threads")).lower() != "threads":
            continue
        filtered.append(row)
    return client, filtered


def main() -> int:
    parser = argparse.ArgumentParser(description="collect Threads metrics safely")
    parser.add_argument("--account-id", default="all", choices=["all", "night_scout", "liver_manager", "beauty_account"])
    parser.add_argument("--result-id")
    parser.add_argument("--source", default="unavailable", choices=["api", "browser", "manual", "unavailable"])
    parser.add_argument("--confidence", default="none", choices=["none", "low", "medium", "high"])
    for key in METRIC_KEYS:
        parser.add_argument(f"--{key.replace('_', '-')}", dest=key)
    parser.add_argument("--memo", default="")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm-metrics", action="store_true")
    parser.add_argument("--use-sheets", action="store_true")
    args = parser.parse_args()

    if args.account_id == "beauty_account":
        print(json.dumps({"status": "BLOCKED", "reason": "beauty_account metrics collection is disabled"}, ensure_ascii=False))
        return 1

    supplied = {key: parse_metric(getattr(args, key)) for key in METRIC_KEYS}
    if any(v is not None and v < 0 for v in supplied.values()):
        print(json.dumps({"status": "BLOCKED", "reason": "metrics must be >= 0"}, ensure_ascii=False))
        return 1

    client, rows = load_rows(args.use_sheets and (args.apply or args.dry_run), args.result_id, args.account_id)
    if not rows:
        rows = [{"result_id": args.result_id or "sample_result", "account_id": args.account_id, "platform": "threads", "post_url": ""}]

    snapshots = []
    for row in rows:
        metrics = supplied if any(v is not None for v in supplied.values()) else {k: None for k in METRIC_KEYS}
        source = args.source if any(v is not None for v in metrics.values()) else "unavailable"
        confidence = args.confidence if any(v is not None for v in metrics.values()) else "none"
        memo = args.memo or ("operator supplied metrics" if source != "unavailable" else "metrics unavailable; no values fabricated")
        snapshots.append(build_snapshot(row=row, source=source, confidence=confidence, metrics=metrics, memo=memo))

    if not args.apply:
        print(json.dumps({"status": "PLAN_ONLY", "snapshot_count": len(snapshots), "snapshots": snapshots}, ensure_ascii=False, indent=2))
        return 0
    if not args.confirm_metrics:
        print(json.dumps({"status": "BLOCKED", "reason": "--apply requires --confirm-metrics"}, ensure_ascii=False))
        return 1
    if client is None:
        print(json.dumps({"status": "BLOCKED", "reason": "--apply requires --use-sheets"}, ensure_ascii=False))
        return 1

    appended = 0
    for snap in snapshots:
        if _append_row(client, "metric_snapshots", snap):
            appended += 1
        if snap["metrics_status"] in {"PARTIAL", "MEASURED", "UNAVAILABLE"}:
            _update_posted_result(client, str(snap["result_id"]), snap)
    print(json.dumps({"status": "APPLIED", "snapshot_count": appended, "result_ids": [s["result_id"] for s in snapshots]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
