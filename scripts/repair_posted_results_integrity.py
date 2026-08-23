#!/usr/bin/env python3
"""repair_posted_results_integrity.py — posted_results の空フィールドを安全に補正する。

対象:
  POSTED 行  : metrics_status="" → "PENDING", real_post="" → "true", media_used="" → "false"
  RECOVERED 行: metrics_status="" → "MANUAL_PENDING", real_post="" → "true", media_used="" → "false"
  status 空   : platform=threads かつ manual_memo に Threads 記録がある → status="RECOVERED"

--dry-run では Sheets に書かない。--apply のときだけ書き込む。
実投稿・SNS 操作・download/upload は一切行わない。
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from config_loader import get_config  # noqa: E402
from sheets_client import SheetsClient, _col_letter  # noqa: E402

JST = timezone(timedelta(hours=9))
ALLOWED_STATUS = {"POSTED", "RECOVERED"}
ALLOWED_METRICS = {"PENDING", "MEASURED", "MANUAL_PENDING"}


def now_iso() -> str:
    return datetime.now(JST).replace(microsecond=0).isoformat()


def repair(client: SheetsClient, dry_run: bool) -> list[dict[str, Any]]:
    """posted_results の全行を監査し、空フィールドを補正する。"""
    ws = client._ws("posted_results")
    headers: list[str] = ws.row_values(1)
    rows: list[dict] = ws.get_all_records()

    repairs: list[dict[str, Any]] = []

    for idx, row in enumerate(rows, start=2):
        raw_status = str(row.get("status", "")).strip()
        status = raw_status.upper()
        platform = str(row.get("platform", "")).lower()
        result_id = str(row.get("result_id", f"row_{idx}"))

        # threads 行以外はスキップ
        if platform != "threads":
            # status が空で manual_memo に threads 記録がある行は threads 行とみなす
            memo = str(row.get("manual_memo", "")).lower()
            if not ("threads" in memo or "スレッズ" in memo):
                continue
            platform = "threads"

        # status が空の行を RECOVERED に補正
        effective_status = status
        changes: dict[str, str] = {}
        if not raw_status:
            memo = str(row.get("manual_memo", "")).lower()
            if "threads" in memo or "スレッズ" in memo or "投稿" in memo:
                effective_status = "RECOVERED"
                changes["status"] = "RECOVERED"
                changes["platform"] = "threads"
            else:
                continue  # 不明な行はスキップ

        if effective_status not in ALLOWED_STATUS:
            continue

        # metrics_status 補正
        metrics_status = str(row.get("metrics_status", "")).strip()
        if not metrics_status or metrics_status.upper() not in ALLOWED_METRICS:
            target = "PENDING" if effective_status == "POSTED" else "MANUAL_PENDING"
            changes["metrics_status"] = target

        # real_post 補正（表記揺れ正規化も含む）
        real_post_raw = str(row.get("real_post", "")).strip()
        real_post_lower = real_post_raw.lower()
        if not real_post_raw or real_post_lower not in ("true", "false"):
            changes["real_post"] = "true"

        # media_used 補正
        media_used_raw = str(row.get("media_used", "")).strip()
        media_used_lower = media_used_raw.lower()
        if not media_used_raw or media_used_lower not in ("true", "false"):
            changes["media_used"] = "false"
        # gspread returns USER_ENTERED booleans as Python True/False. Their
        # string forms are valid and must not be rewritten on every worker run.

        if not changes:
            continue

        repairs.append({
            "row_idx": idx,
            "result_id": result_id,
            "status": effective_status,
            "changes": changes,
        })

    if not dry_run and repairs:
        updates = []
        for item in repairs:
            for field, value in item["changes"].items():
                if field not in headers:
                    continue
                column = _col_letter(headers.index(field) + 1)
                updates.append({"range": f"{column}{item['row_idx']}", "values": [[value]]})
        if updates:
            # One Sheets API request keeps this preflight below the per-minute
            # write quota even when historical rows need several fields fixed.
            ws.batch_update(updates, value_input_option="USER_ENTERED")

    return repairs


def _log_repairs(client: SheetsClient, repairs: list[dict[str, Any]], dry_run: bool) -> None:
    if not repairs or dry_run:
        return
    try:
        ws = client._ws("logs")
        headers: list[str] = ws.row_values(1)
        summary = f"repair_posted_results: {len(repairs)}行補正 / " + ", ".join(
            f"{r['result_id']}[{','.join(r['changes'].keys())}]" for r in repairs
        )
        row_data = {
            "log_id": f"repair-{now_iso().replace(':', '-')}",
            "created_at": now_iso(),
            "account_id": "system",
            "action": "repair_posted_results_integrity",
            "status": "COMPLETED",
            "summary": summary,
            "notes": "dry_run=false",
        }
        ws.append_row([str(row_data.get(h, "")) for h in headers])
    except Exception as e:
        print(f"[WARN] logs 書き込み失敗（修復自体は完了）: {e}", file=sys.stderr)


def audit(client: SheetsClient) -> list[dict[str, Any]]:
    """修復なしで監査結果だけ返す。"""
    ws = client._ws("posted_results")
    rows: list[dict] = ws.get_all_records()
    result = []
    for idx, row in enumerate(rows, start=2):
        result_id = str(row.get("result_id", f"row_{idx}"))
        account_id = str(row.get("account_id", ""))
        status = str(row.get("status", "")).strip()
        platform = str(row.get("platform", "")).lower()
        metrics_status = str(row.get("metrics_status", "")).strip()
        real_post = str(row.get("real_post", "")).strip()
        media_used = str(row.get("media_used", "")).strip()
        external_id = str(row.get("external_post_id", "")).strip()
        post_url = str(row.get("post_url", "")).strip()
        issues = []
        if not metrics_status or metrics_status.upper() not in {"PENDING", "MEASURED", "MANUAL_PENDING"}:
            issues.append(f"metrics_status={metrics_status!r}")
        if status.upper() == "POSTED" and real_post.lower() != "true":
            issues.append(f"real_post={real_post!r}")
        if status.upper() == "POSTED" and media_used.lower() != "false":
            issues.append(f"media_used={media_used!r}")
        result.append({
            "row": idx,
            "result_id": result_id,
            "account_id": account_id,
            "platform": platform,
            "status": status,
            "metrics_status": metrics_status or "(empty)",
            "real_post": real_post or "(empty)",
            "media_used": media_used or "(empty)",
            "external_post_id": external_id or "(empty)",
            "post_url": post_url or "(empty)",
            "issues": issues,
        })
    return result


def main() -> int:
    parser = argparse.ArgumentParser(
        description="posted_results の空フィールドを安全に補正する"
    )
    parser.add_argument("--dry-run", action="store_true", help="Sheets に書き込まない")
    parser.add_argument("--apply", action="store_true", help="Sheets に書き込む")
    parser.add_argument("--audit", action="store_true", help="監査結果だけ表示（補正なし）")
    args = parser.parse_args()

    if not args.dry_run and not args.apply and not args.audit:
        parser.error("--dry-run / --apply / --audit のいずれかを指定してください")

    cfg = get_config()
    dry_run = not args.apply
    client = SheetsClient(cfg["sheet_id"], cfg["sa_dict"], dry_run=dry_run)

    print("=== repair_posted_results_integrity ===")
    print(f"mode={'DRY_RUN' if dry_run else 'APPLY'}")

    if args.audit:
        rows = audit(client)
        print(f"\n--- posted_results 監査結果 ({len(rows)} 行) ---")
        for r in rows:
            print(f"  row={r['row']} result_id={r['result_id']} account={r['account_id']}"
                  f" status={r['status']} platform={r['platform']}")
            print(f"    metrics_status={r['metrics_status']} real_post={r['real_post']}"
                  f" media_used={r['media_used']}")
            print(f"    external_post_id={r['external_post_id']} post_url={r['post_url']}")
            if r["issues"]:
                print(f"    [ISSUE] {', '.join(r['issues'])}")
        return 0

    repairs = repair(client, dry_run=dry_run)

    if not repairs:
        print("[OK] 補正対象なし")
        return 0

    print(f"\n{'[DRY-RUN] 補正予定' if dry_run else '[APPLIED] 補正完了'}: {len(repairs)} 行")
    for r in repairs:
        print(f"  row={r['row_idx']} result_id={r['result_id']}"
              f" status={r['status']} changes={r['changes']}")

    if not dry_run:
        _log_repairs(client, repairs, dry_run=False)

        # read-after-write 確認
        ws = client._ws("posted_results")
        rows_after = ws.get_all_records()
        bad = []
        for row in rows_after:
            platform = str(row.get("platform", "")).lower()
            status = str(row.get("status", "")).upper()
            if platform != "threads" or status not in {"POSTED", "RECOVERED"}:
                continue
            m = str(row.get("metrics_status", "")).upper()
            if m not in {"PENDING", "MEASURED", "MANUAL_PENDING"}:
                bad.append(f"{row.get('result_id')} metrics_status={m!r}")
            if status == "POSTED":
                if str(row.get("real_post", "")).lower() != "true":
                    bad.append(f"{row.get('result_id')} real_post={row.get('real_post')!r}")
                # Both text-only (false) and authorized media posts (true) are
                # valid. Rights/provenance for true rows is enforced by the
                # production Sheets verifier; this repair only normalizes the
                # boolean integrity field.
                if str(row.get("media_used", "")).lower() not in {"true", "false"}:
                    bad.append(f"{row.get('result_id')} media_used={row.get('media_used')!r}")
        if bad:
            print(f"[WARN] read-after-write で残課題あり: {bad}", file=sys.stderr)
            return 1
        print("[OK] read-after-write 確認: 問題なし")

    return 0


if __name__ == "__main__":
    sys.exit(main())
