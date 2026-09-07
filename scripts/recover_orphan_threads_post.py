#!/usr/bin/env python3
"""recover_orphan_threads_post.py — Threads孤児投稿の復旧スクリプト。

目的: Threads投稿は成功したがSheets保存（posted_results/queue更新）が失敗した
ケースを再投稿なしで復旧する。

絶対ルール:
- 再投稿は絶対にしない
- 既存posted_resultsの補正は --repair-existing-save と実API照合が必要
- secret/token値を表示しない
- apply しない限り Sheets は書き変わらない

モード:
  --dry-run (default)  : Sheets/API を読み取りのみ。変更なし。
  --apply              : posted_results 追加、queue 更新、logs/pdca 追記。

使い方:
  # Threads API で最新投稿を取得して候補表示
  python3 scripts/recover_orphan_threads_post.py \\
      --account-id night_scout \\
      --queue-id recovery_night_scout_queue_01 \\
      --dry-run

  # 外部投稿IDが分かっている場合（API 不要）
  python3 scripts/recover_orphan_threads_post.py \\
      --account-id night_scout \\
      --queue-id recovery_night_scout_queue_01 \\
      --external-post-id 1234567890 \\
      --post-url "https://www.threads.net/@username/post/..." \\
      --apply

  # 外部投稿IDなし（post_url も不明）で確定する場合
  python3 scripts/recover_orphan_threads_post.py \\
      --account-id night_scout \\
      --queue-id recovery_night_scout_queue_01 \\
      --apply
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from config_loader import get_config  # noqa: E402
from publishers.threads_credentials import resolve_credentials  # noqa: E402
from sheets_client import SheetsClient  # noqa: E402


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ws(client: SheetsClient, logical: str):
    return client._ws(logical)


def _get_headers_with_retry(ws, retries: int = 4) -> list[str]:
    delays = [0, 5, 15, 30]
    for attempt in range(retries):
        d = delays[attempt] if attempt < len(delays) else 30
        if d > 0:
            print(f"  [RETRY] Sheets 429; waiting {d}s (attempt {attempt + 1}/{retries})")
            time.sleep(d)
        try:
            return ws.row_values(1)
        except Exception as exc:
            msg = str(exc).lower()
            if "429" in msg or "quota" in msg:
                if attempt < retries - 1:
                    continue
            raise
    return []


def _get_records(client: SheetsClient, logical: str) -> list[dict[str, Any]]:
    return [
        dict(r)
        for r in client._call_with_rate_limit_retry(
            f"get_all_records:{logical}:orphan_recovery",
            lambda: _ws(client, logical).get_all_records(),
        )
    ]


def _append_row(client: SheetsClient, logical: str, row: dict[str, Any]) -> None:
    ws = _ws(client, logical)
    headers = _get_headers_with_retry(ws)
    client._call_with_rate_limit_retry(
        f"append_row:{logical}:orphan_recovery",
        lambda: ws.append_row([str(row.get(h, "")) for h in headers], value_input_option="USER_ENTERED"),
    )


def _update_row(client: SheetsClient, logical: str, key: str, key_value: str, fields: dict[str, Any]) -> bool:
    ws = _ws(client, logical)
    headers = _get_headers_with_retry(ws)
    if key not in headers:
        raise KeyError(f"{logical}: missing key header {key!r}")
    cell = client._call_with_rate_limit_retry(
        f"find:{logical}:{key_value}:orphan_recovery",
        lambda: ws.find(key_value, in_column=headers.index(key) + 1),
    )
    if cell is None:
        return False
    client._batch_update_fields(
        ws,
        headers,
        cell.row,
        fields,
        label=f"{logical}:{key_value}:orphan_recovery",
    )
    return True


def _fetch_recent_threads_posts(account_id: str, limit: int = 25) -> list[dict]:
    """Threads Graph API で最新投稿を取得する。"""
    import requests

    creds = resolve_credentials(account_id)
    access_token = creds.get("access_token", "")
    user_id = creds.get("user_id", "")
    if not access_token or not user_id:
        raise RuntimeError(f"Threads認証情報が不足: account_id={account_id} (secretを確認してください)")

    url = f"https://graph.threads.net/v1.0/{user_id}/threads"
    params = {
        "fields": "id,text,timestamp,permalink",
        "limit": str(limit),
    }
    headers = {"Authorization": f"Bearer {access_token}"}
    try:
        resp = requests.get(url, params=params, headers=headers, timeout=30)
        resp.raise_for_status()
    except requests.HTTPError as exc:
        raise RuntimeError(f"Threads API error: status={exc.response.status_code}") from None
    data = resp.json()
    return data.get("data", [])


def _text_for_queue_id(
    client: SheetsClient,
    queue_row: dict[str, Any],
) -> str:
    draft_id = str(queue_row.get("draft_id", ""))
    social_rows = _get_records(client, "social_derivatives")
    for row in social_rows:
        if row.get("draft_id") == draft_id and str(row.get("platform", "")).lower() == "threads":
            t = str(row.get("text", "")).strip()
            if t:
                return t
    draft_rows = _get_records(client, "drafts")
    for row in draft_rows:
        if row.get("draft_id") == draft_id:
            for key in ("body_md", "content"):
                t = str(row.get(key, "")).strip()
                if t:
                    return t
    return ""


def _check_already_recovered(
    posted_rows: list[dict],
    queue_id: str,
    draft_id: str,
    derivative_id: str,
) -> str | None:
    for r in posted_rows:
        if str(r.get("queue_id", "")) == queue_id:
            return f"queue_id={queue_id} は posted_results に既存 (result_id={r.get('result_id')})"
        status = str(r.get("status", "")).upper()
        if str(r.get("draft_id", "")) == draft_id and status in {"POSTED", "RECOVERED"}:
            return f"draft_id={draft_id} は posted_results に status={status} で既存 (result_id={r.get('result_id')})"
        if derivative_id and str(r.get("derivative_id", "")) == derivative_id:
            return f"derivative_id={derivative_id} は posted_results に既存 (result_id={r.get('result_id')})"
    return None


def _match_post_in_api_results(
    api_posts: list[dict],
    expected_text: str,
) -> dict | None:
    expected_norm = expected_text.strip()
    for post in api_posts:
        actual = str(post.get("text", "")).strip()
        if actual == expected_norm:
            return post
        if len(expected_norm) > 20 and expected_norm[:20] in actual:
            return post
    return None


def _write_recovery(
    client: SheetsClient,
    *,
    queue_row: dict[str, Any],
    social_derivative_id: str,
    text: str,
    external_post_id: str,
    post_url: str,
    dry_run: bool,
) -> dict[str, Any]:
    queue_id = str(queue_row.get("queue_id", ""))
    account_id = str(queue_row.get("account_id", ""))
    draft_id = str(queue_row.get("draft_id", ""))
    result_id = f"orphan_recovery_{queue_id}_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"

    permalink_note = " permalink_pending=true" if not post_url else ""
    ext_id_note = " external_post_id_pending=true" if not external_post_id else ""

    posted_result_row = {
        "result_id": result_id,
        "queue_id": queue_id,
        "draft_id": draft_id,
        "derivative_id": social_derivative_id,
        "account_id": account_id,
        "platform": "threads",
        "external_post_id": external_post_id,
        "post_url": post_url,
        "posted_text": text,
        "posted_at": queue_row.get("processed_at") or _now_iso(),
        "status": "RECOVERED",
        "metrics_status": "MANUAL_PENDING",
        "real_post": "true",
        "media_used": "false",
        "source_queue_status": str(queue_row.get("status", "")),
        "save_source": "recover_orphan_threads_post",
        "created_by": "recover_orphan_threads_post",
        "measurement_window": "pending",
        # Unknown metrics remain blank. A confirmed zero must come from a
        # metrics collector or human import, never from recovery.
        "views": "",
        "likes": "",
        "comments": "",
        "follows": "",
        "profile_clicks": "",
        "line_adds": "",
        "manual_memo": (
            f"Orphan recovery: Threads投稿は成功したがSheets保存が失敗したため復旧。"
            f"{permalink_note}{ext_id_note}"
        ),
        "collected_at": _now_iso(),
    }

    queue_update_fields = {
        "status": "POSTED",
        "error": "ORPHAN_RECOVERED",
        "processed_at": _now_iso(),
    }

    log_row = {
        "log_id": f"orphan_recovery_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}",
        "timestamp": _now_iso(),
        "account_id": account_id,
        "operation": "recover_orphan_threads_post",
        "level": "INFO",
        "status": "RECOVERED",
        "message": f"Orphan post recovered: queue_id={queue_id}",
        "details": json.dumps({"queue_id": queue_id, "result_id": result_id, "external_post_id_known": bool(external_post_id)}, ensure_ascii=False),
    }

    pdca_row = {
        "run_id": f"pdca_orphan_{result_id}",
        "account_id": account_id,
        "total_results": "1",
        "suggestion_count": "1",
        "notes": f"Orphan recovery: queue_id={queue_id}",
        "created_at": _now_iso(),
    }

    suggestion_row = {
        "suggestion_id": f"sug_orphan_{result_id}",
        "account_id": account_id,
        "created_at": _now_iso(),
        "source": "recover_orphan_threads_post",
        "suggestion_type": "metrics_followup",
        "target_template": "",
        "current_behavior": "Orphan post recovered. Metrics not imported yet.",
        "suggested_change": "Import Threads metrics manually (import_threads_metrics_manual.py).",
        "reason": f"result_id={result_id} は RECOVERED 状態のため手動メトリクス確認が必要",
        "expected_impact": "Enable human-reviewed PDCA loop.",
        "priority": "high",
        "status": "WAITING_REVIEW",
        "reviewed_by": "",
        "reviewed_at": "",
        "notes": "auto_apply=false; do not activate learning rule automatically.",
    }

    if dry_run:
        return {
            "status": "DRY_RUN",
            "read_only": True,
            "queue_id": queue_id,
            "result_id": result_id,
            "would_write": {
                # Recovery previews are operational telemetry. Keep the post
                # body and permalink out of stdout while still showing the
                # exact state transition that would be written.
                "posted_results": {
                    "result_id": result_id,
                    "queue_id": queue_id,
                    "account_id": account_id,
                    "platform": "threads",
                    "status": "RECOVERED",
                    "metrics_status": "MANUAL_PENDING",
                    "external_post_id_known": bool(external_post_id),
                    "post_url_known": bool(post_url),
                    "posted_text_length": len(text),
                },
                "queue_update": queue_update_fields,
                "log": {"log_id": log_row["log_id"]},
            },
        }

    _append_row(client, "posted_results", posted_result_row)
    print(f"  [WRITE] posted_results: result_id={result_id}")

    updated = _update_row(client, "queue", "queue_id", queue_id, queue_update_fields)
    print(f"  [WRITE] queue: queue_id={queue_id} status=POSTED updated={updated}")

    _append_row(client, "logs", log_row)
    _append_row(client, "pdca_runs", pdca_row)
    _append_row(client, "prompt_improvement_suggestions", suggestion_row)

    return {
        "status": "RECOVERED",
        "queue_id": queue_id,
        "result_id": result_id,
        "external_post_id": external_post_id,
        "post_url": post_url,
    }


def repair_existing_save(client: SheetsClient, queue: dict[str, Any], api_posts: list[dict], *, apply: bool) -> dict[str, Any]:
    from process_threads_queue import records, update_row, schedule_metrics_after_post, verify_posted_result_persistence
    from content_slot_runs import build_slot_run, upsert_slot_run

    queue_id, account = str(queue["queue_id"]), str(queue["account_id"])
    if queue.get("status") != "POSTED_SAVE_UNVERIFIED" or queue.get("error") != "EXTERNAL_POST_ID_MISMATCH":
        return {"status": "BLOCKED", "reason": "NOT_AN_IDENTIFIER_SAVE_FAILURE"}
    rows = [r for r in records(client, "posted_results") if str(r.get("queue_id", "")) == queue_id]
    if len(rows) != 1 or rows[0].get("account_id") != account or rows[0].get("status") != "POSTED":
        return {"status": "BLOCKED", "reason": "AMBIGUOUS_POSTED_RESULT"}
    row = rows[0]
    text, url = str(row.get("posted_text", "")), str(row.get("post_url", ""))
    matches = [p for p in api_posts if url and p.get("permalink") == url
               and text and p.get("text") == text and str(p.get("id", "")).isdigit()]
    if len(matches) != 1 or str(queue.get("public_post_text", "")) != text:
        return {"status": "BLOCKED", "reason": "LIVE_POST_EXACT_MATCH_REQUIRED"}
    try:
        posted_at = datetime.fromisoformat(str(row["posted_at"]).replace("Z", "+00:00"))
        remote_at = datetime.fromisoformat(str(matches[0]["timestamp"]).replace("Z", "+00:00"))
        if posted_at.tzinfo is None or remote_at.tzinfo is None or abs((posted_at - remote_at).total_seconds()) > 120:
            raise ValueError("timestamp mismatch")
    except (KeyError, ValueError):
        return {"status": "BLOCKED", "reason": "LIVE_POST_TIMESTAMP_MISMATCH"}
    exact_id, result_id = str(matches[0]["id"]), str(row["result_id"])
    result = {"status": "PLAN_ONLY", "queue_id": queue_id, "result_id": result_id,
              "external_post_id": exact_id, "post_url": url, "would_post": False}
    if not apply:
        return result
    if not update_row(client, "posted_results", "result_id", result_id, {"external_post_id": exact_id}):
        raise RuntimeError("identifier_update_failed")
    check = verify_posted_result_persistence(records(client, "posted_results"), result_id=result_id,
            queue_id=queue_id, account_id=account, external_post_id=exact_id)
    if check["status"] != "PASS":
        raise RuntimeError("identifier_read_after_write_failed")
    if not update_row(client, "posted_results", "result_id", result_id,
                      {"verification_status": "READ_AFTER_WRITE_PASS", "verification_checked_at": _now_iso()}):
        raise RuntimeError("verification_update_failed")
    verified = [r for r in records(client, "posted_results") if r.get("result_id") == result_id]
    if len(verified) != 1 or verified[0].get("verification_status") != "READ_AFTER_WRITE_PASS":
        raise RuntimeError("verification_read_after_write_failed")
    schedule_metrics_after_post(client, result_id)
    jobs = [j for j in records(client, "metrics_collection_jobs") if j.get("result_id") == result_id]
    if len(jobs) != 3 or any(j.get("account_id") != account for j in jobs) or {int(j.get("window_hours") or 0) for j in jobs if j.get("status") not in {"FAILED", "CANCELLED"}} != {24, 72, 168}:
        raise RuntimeError("metrics_reservation_read_after_write_failed")
    if queue.get("slot_id"):
        slot = build_slot_run(account, str(queue["slot_id"]), now=posted_at,
                status="POSTED_PRIMARY", actual_post_type=str(queue.get("generation_mode", "")),
                queue_id=queue_id, result_id=result_id, post_url=url,
                media_asset_id=str(row.get("media_asset_id", "")), actual_posted_at=str(row["posted_at"]))
        saved = upsert_slot_run(client, slot)
        if saved.get("status") not in {"UPDATED", "CREATED"}:
            raise RuntimeError("slot_recovery_save_failed")
    if not update_row(client, "queue", "queue_id", queue_id, {"status": "POSTED", "error": "", "result_id": result_id}):
        raise RuntimeError("queue_recovery_update_failed")
    after = next((r for r in records(client, "queue") if r.get("queue_id") == queue_id), {})
    if after.get("status") != "POSTED":
        raise RuntimeError("queue_recovery_read_after_write_failed")
    return {**result, "status": "RECOVERED", "read_after_write": "PASS", "metrics_reservation_count": len(jobs)}


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Threads孤児投稿復旧: 投稿成功・Sheets保存失敗のケースを再投稿なしで復旧する"
    )
    parser.add_argument("--account-id", required=True, choices=["night_scout", "liver_manager"], help="対象アカウント")
    parser.add_argument("--queue-id", required=True, help="復旧対象の queue_id")
    parser.add_argument("--external-post-id", default="", help="既知のThreads post ID（省略時はAPI検索）")
    parser.add_argument("--post-url", default="", help="既知のThreads投稿URL（省略可）")
    parser.add_argument("--apply", action="store_true", help="Sheetsへの書き込みを実行する（省略時はdry-run）")
    parser.add_argument("--skip-api-lookup", action="store_true", help="Threads API検索をスキップ（APIなしで確定する場合）")
    parser.add_argument("--repair-existing-save", action="store_true")
    args = parser.parse_args()

    dry_run = not args.apply
    print(f"[recover_orphan_threads_post] account_id={args.account_id} queue_id={args.queue_id} dry_run={dry_run}")

    cfg = get_config()
    client = SheetsClient(cfg["sheet_id"], cfg["sa_dict"], dry_run=False)

    # キュー行を取得
    queue_rows = _get_records(client, "queue")
    queue_row = next((r for r in queue_rows if str(r.get("queue_id", "")) == args.queue_id), None)
    if not queue_row:
        print(f"[ERROR] queue_id={args.queue_id} が 投稿キュー に見つかりません")
        return 1

    print(f"  queue_id={args.queue_id} status={queue_row.get('status')} draft_id={queue_row.get('draft_id')}")

    if str(queue_row.get("account_id", "")) != args.account_id:
        print(f"[ERROR] queue の account_id={queue_row.get('account_id')} が {args.account_id} と不一致")
        return 1

    if args.repair_existing_save:
        if args.skip_api_lookup or args.external_post_id or args.post_url:
            raise RuntimeError("existing_save_repair_requires_live_api_not_supplied_identity")
        result = repair_existing_save(client, queue_row, _fetch_recent_threads_posts(args.account_id, 25), apply=args.apply)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["status"] in {"PLAN_ONLY", "RECOVERED"} else 2

    # 安全チェック: 既に復旧済みでないか
    posted_rows = _get_records(client, "posted_results")
    social_rows = _get_records(client, "social_derivatives")
    social = next(
        (r for r in social_rows
         if r.get("draft_id") == queue_row.get("draft_id")
         and str(r.get("platform", "")).lower() == "threads"),
        None,
    )
    social_derivative_id = social.get("derivative_id", "") if social else ""

    already = _check_already_recovered(
        posted_rows,
        queue_id=args.queue_id,
        draft_id=str(queue_row.get("draft_id", "")),
        derivative_id=social_derivative_id,
    )
    if already:
        print(f"[SKIP] 既に復旧済み: {already}")
        return 0

    # 投稿テキスト取得
    text = _text_for_queue_id(client, queue_row)
    if not text:
        print(f"[ERROR] queue_id={args.queue_id} の投稿テキストが見つかりません")
        return 1
    print(f"  expected_text_len={len(text)}")

    external_post_id = args.external_post_id
    post_url = args.post_url

    # Threads API で投稿候補を検索（ID不明かつAPIスキップ不要の場合）
    if not external_post_id and not args.skip_api_lookup:
        print(f"  [LOOKUP] Threads API で最新投稿を検索します (account_id={args.account_id})")
        try:
            api_posts = _fetch_recent_threads_posts(args.account_id, limit=25)
            matched = _match_post_in_api_results(api_posts, text)
            if matched:
                external_post_id = str(matched.get("id", ""))
                post_url = str(matched.get("permalink", ""))
                print(f"  [MATCH] Threads投稿が一致: external_post_id={external_post_id}")
            else:
                print(f"  [NO_MATCH] APIの最新{len(api_posts)}件にテキスト一致なし")
                print("  --external-post-id または --skip-api-lookup を指定して再実行してください")
                if dry_run:
                    print("  [DRY_RUN] 情報確認完了。一致なしのため apply 不可。")
                    return 0
                else:
                    print("[BLOCKED] テキスト一致なし・external-post-id 未指定のため apply を中断します")
                    return 1
        except Exception as exc:
            print(f"  [WARN] Threads API 検索に失敗: {exc}")
            print("  --external-post-id または --skip-api-lookup を指定して再実行してください")
            if dry_run:
                print("  [DRY_RUN] API失敗のまま継続はしません。")
                return 0
            else:
                print("[BLOCKED] Threads API 失敗のため apply を中断します")
                return 1
    elif args.skip_api_lookup and not external_post_id:
        print("  [SKIP_API] Threads API検索スキップ。external_post_id は空のまま復旧します。")

    # 復旧実行
    outcome = _write_recovery(
        client,
        queue_row=queue_row,
        social_derivative_id=social_derivative_id,
        text=text,
        external_post_id=external_post_id,
        post_url=post_url,
        dry_run=dry_run,
    )
    print(json.dumps(outcome, ensure_ascii=False, indent=2))

    if dry_run:
        print("\n[DRY_RUN] 実際の書き込みは行いませんでした。--apply を付けて再実行すると復旧を実行します。")
    else:
        print(f"\n[DONE] 復旧完了: result_id={outcome.get('result_id')}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
