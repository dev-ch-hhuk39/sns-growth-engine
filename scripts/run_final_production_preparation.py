#!/usr/bin/env python3
"""One bounded command for source preparation, repair checks and canary readiness.

This is deliberately *not* a publisher.  It may collect approved reference
posts and quarantine stale local operational state only after an explicit
confirmation.  It never downloads media, uploads assets, cuts video or posts.
X is an optional source: a missing bearer token is reported as
``BLOCKED_OPTIONAL`` and does not prevent Threads/manual-import preparation.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from audit_media_permissions import build_report as permission_report
from build_live_canary_inventory import _rows, build_inventory
from final_production_contracts import source_integrity_report


def _run(command: list[str]) -> dict[str, Any]:
    completed = subprocess.run(command, cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    payload: dict[str, Any]
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError:
        payload = {"status": "UNPARSEABLE", "stdout_tail": completed.stdout[-500:], "stderr_tail": completed.stderr[-500:]}
    return {"exit_code": completed.returncode, "result": payload}


def _sources(account_id: str) -> list[dict[str, Any]]:
    data = json.loads((ROOT / "config/source_accounts/default_sources.json").read_text(encoding="utf-8"))
    selected = []
    for source in data.get("sources", []):
        targets = source.get("target_account_ids") or [source.get("target_account_id")]
        if account_id != "all" and account_id not in targets:
            continue
        if str(source.get("fetch_enabled", "")).lower() not in {"true", "1"}:
            continue
        platform = str(source.get("source_platform") or source.get("platform") or "").lower()
        if platform in {"threads", "x"}:
            selected.append(source)
    return selected


def _manual_args(values: list[str]) -> list[tuple[str, Path]]:
    result = []
    for value in values:
        source_id, marker, raw_path = value.partition("=")
        path = Path(raw_path)
        if marker and source_id and path.exists():
            result.append((source_id, path))
    return result


def build_report(*, account_id: str, apply: bool, manual_json: list[str]) -> dict[str, Any]:
    collect_base = [sys.executable, "scripts/collect_source_posts.py", "--account-id", account_id, "--limit", "10"]
    if apply:
        collect_base.extend(["--apply", "--confirm-collect", "--use-sheets"])
    else:
        collect_base.append("--dry-run")
    sources = _sources(account_id)
    threads_ids = [str(item.get("source_id", "")) for item in sources if str(item.get("source_platform") or item.get("platform") or "").lower() == "threads"]
    x_ids = [str(item.get("source_id", "")) for item in sources if str(item.get("source_platform") or item.get("platform") or "").lower() == "x"]
    collection: dict[str, Any] = {}
    if threads_ids:
        command = collect_base + ["--platform", "threads", "--fetch-real"] + sum((["--source-id", item] for item in threads_ids), [])
        collection["threads"] = _run(command)
    else:
        collection["threads"] = {"exit_code": 0, "result": {"status": "NO_ENABLED_THREADS_SOURCES"}}
    if x_ids:
        if os.environ.get("X_READ_ONLY_BEARER_TOKEN"):
            command = collect_base + ["--platform", "x", "--include-x", "--fetch-real"] + sum((["--source-id", item] for item in x_ids), [])
            collection["x"] = _run(command)
        else:
            collection["x"] = {"exit_code": 0, "result": {"status": "BLOCKED_OPTIONAL", "reason": "X_READ_ONLY_BEARER_TOKEN missing; Threads/manual import continue", "source_ids": x_ids}}
    for source_id, path in _manual_args(manual_json):
        source = next((item for item in sources if str(item.get("source_id", "")) == source_id), {})
        platform = str(source.get("source_platform") or "threads")
        command = collect_base + ["--platform", platform, "--source-id", source_id, "--manual-json", str(path)]
        collection[f"manual_{source_id}"] = _run(command)
    datasets, sheets_status = _rows(True)
    quarantine_plan = _run([sys.executable, "scripts/quarantine_stale_operational_rows.py", "--older-than-minutes", "120", "--use-sheets"])
    if apply:
        # Reuse the existing hardened executor rather than duplicating its
        # row-level mutation rules. It is still limited to stale statuses.
        collection["stale_quarantine"] = _run([sys.executable, "scripts/quarantine_stale_operational_rows.py", "--older-than-minutes", "120", "--apply", "--confirm-quarantine", "--use-sheets"])
        datasets, sheets_status = _rows(True)
        quarantine_plan = _run([sys.executable, "scripts/quarantine_stale_operational_rows.py", "--older-than-minutes", "120", "--use-sheets"])
    report = {
        "status": "APPLIED_PREPARATION" if apply else "PLAN_ONLY",
        "account_id": account_id,
        "collection": collection,
        "source_read_after_write": source_integrity_report(datasets.get("source_posts", []), datasets.get("source_post_media", []), source_ids=set(threads_ids + x_ids)),
        "stale_operational_rows": quarantine_plan["result"],
        "permission_audit": permission_report(use_sheets=True),
        "canary_inventory": build_inventory(datasets),
        "manual_json_template": str(ROOT / "docs/manual-source-import-template.json"),
        "sheets_status": sheets_status,
        "would_download": False, "would_cut": False, "would_upload": False, "would_post": False,
    }
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--account-id", choices=["all", "night_scout", "liver_manager"], default="all")
    parser.add_argument("--manual-json", action="append", default=[], metavar="SOURCE_ID=PATH")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm-production-preparation", action="store_true")
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()
    if args.apply and not args.confirm_production_preparation:
        print(json.dumps({"status": "BLOCKED", "reason": "--apply requires --confirm-production-preparation", "would_post": False})); return 1
    report = build_report(account_id=args.account_id, apply=args.apply, manual_json=args.manual_json)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True); args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"); report["output_path"] = str(args.output)
    print(json.dumps(report, ensure_ascii=False, indent=2)); return 0


if __name__ == "__main__":
    raise SystemExit(main())
