"""
queue_builder.py - social_derivatives から queue を作成するロジック

処理フロー:
  1. social_derivatives.status=READY を取得
  2. draft と account を参照
  3. accounts.auto_publish を見る
  4. publish_decision.should_queue() で queue ステータスを決定
  5. accounts.post_time / timezone から次回 scheduled_at を計算
  6. 重複 queue_id を作らない
  7. queue に保存
  8. logs に記録

queue.status:
  READY          - 自動投稿可（auto_publish=TRUE かつ全条件パス）
  WAITING_REVIEW - キューには積むが手動確認待ち
  REJECTED       - キューに積まない

安全ガード:
  PUBLISH_ENABLED=false（デフォルト）の間、実際の SNS 投稿処理は実行しない。
  Phase 3 で X API / Threads API の投稿処理を追加する際に TRUE に変更する。
"""
from __future__ import annotations

import os
from datetime import date, datetime, time, timedelta, timezone
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

if TYPE_CHECKING:
    from sheets_client import SheetsClient, MockSheetsClient

from publish_decision import should_queue

# 安全ガード: PUBLISH_ENABLED=true になるまで投稿処理は実行しない（Phase 3 以降）
_PUBLISH_ENABLED = os.environ.get("PUBLISH_ENABLED", "false").strip().lower() in ("1", "true", "yes")


def _assert_publish_enabled(operation: str) -> None:
    """実際の SNS 投稿を行う関数の先頭で呼ぶ。PUBLISH_ENABLED=false なら NotImplementedError。"""
    if not _PUBLISH_ENABLED:
        raise NotImplementedError(
            f"{operation}: PUBLISH_ENABLED=false のため投稿処理は実行できません。"
            " Phase 3 実装後に PUBLISH_ENABLED=true を設定してください。"
        )


def build_queue(
    sheets: "SheetsClient | MockSheetsClient",
    account_id: str | None = None,
    platforms: list[str] | None = None,
    dry_run: bool = False,
) -> list[dict]:
    """READY な social_derivatives を queue に積む。

    Returns: 追加した queue アイテム辞書のリスト。
    """
    if platforms is None:
        platforms = ["x", "threads"]

    results: list[dict] = []
    derivatives = sheets.get_social_derivatives(
        account_id=account_id,
        status="READY",
    )
    if platforms:
        derivatives = [d for d in derivatives if d.get("platform", "").lower() in platforms]

    print(f"\n[queue_builder] READY な derivatives: {len(derivatives)} 件")

    for der in derivatives:
        draft_id = der.get("draft_id", "")
        platform = der.get("platform", "")
        acct_id = der.get("account_id", "")

        # 重複チェック
        existing = sheets.find_queue_item(draft_id, platform)
        if existing is not None:
            print(f"  [skip] 重複 draft_id={draft_id} platform={platform}")
            continue

        draft = _find_draft(sheets, draft_id)
        account = sheets.get_account(acct_id) or {}

        add_to_queue, queue_status, reason = should_queue(der, draft, account)

        if not add_to_queue:
            print(f"  [reject] draft_id={draft_id} platform={platform}: {reason}")
            sheets.log(
                "build_queue", "REJECTED",
                f"queue除外: {reason}",
                account_id=acct_id,
                details=f"draft_id={draft_id} platform={platform}",
            )
            continue

        scheduled_at = _calc_scheduled_at(account)

        item = {
            "draft_id":     draft_id,
            "account_id":   acct_id,
            "platform":     platform,
            "scheduled_at": scheduled_at,
            "priority":     "1",
            "status":       queue_status,
            "error":        "",
        }

        queue_id = sheets.append_queue_item(item)
        item["queue_id"] = queue_id

        sheets.log(
            "build_queue", "OK",
            f"queue追加: platform={platform} status={queue_status}",
            account_id=acct_id,
            details=f"draft_id={draft_id} queue_id={queue_id} scheduled_at={scheduled_at} reason={reason}",
        )

        print(f"  [ok] queue_id={queue_id} platform={platform} status={queue_status} scheduled_at={scheduled_at}")
        results.append(item)

    print(f"\n[queue_builder] queue追加完了: {len(results)} 件")
    return results


def _find_draft(sheets: "SheetsClient | MockSheetsClient", draft_id: str) -> dict:
    """draft_id に対応する draft を取得する。見つからなければ空 dict。"""
    try:
        drafts = sheets.get_drafts()
        for d in drafts:
            if d.get("draft_id") == draft_id:
                return d
    except Exception:
        pass
    return {}


def _calc_scheduled_at(account: dict) -> str:
    """accounts.post_time / timezone から次回投稿日時を計算して ISO8601 文字列を返す。

    post_time 形式: "HH:MM"（例: "20:00"）
    当日の post_time をすでに過ぎていれば翌日に設定する。
    """
    post_time_str = str(account.get("post_time", "20:00")).strip() or "20:00"
    tz_name = str(account.get("timezone", "Asia/Tokyo")).strip() or "Asia/Tokyo"

    try:
        tz = ZoneInfo(tz_name)
    except (ZoneInfoNotFoundError, Exception):
        tz = ZoneInfo("Asia/Tokyo")

    try:
        h, m = (int(x) for x in post_time_str.split(":")[:2])
    except (ValueError, AttributeError):
        h, m = 20, 0

    now_local = datetime.now(tz)
    target_today = datetime(now_local.year, now_local.month, now_local.day, h, m, tzinfo=tz)

    if now_local >= target_today:
        target = target_today + timedelta(days=1)
    else:
        target = target_today

    return target.strftime("%Y-%m-%dT%H:%M:%S%z")
