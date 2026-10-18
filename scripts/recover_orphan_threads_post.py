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
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from config_loader import get_config  # noqa: E402
from publishers.threads_credentials import resolve_credentials  # noqa: E402
from sheets_client import SheetsClient, sheets_write_once  # noqa: E402


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
    # An accepted append followed by a network error is an UNKNOWN outcome.
    # Never blindly replay a potentially accepted result/metric/log insert.
    sheets_write_once(
        f"orphan_recovery_{logical}_append",
        lambda: ws.append_row(
            [str(row.get(h, "")) for h in headers],
            value_input_option="USER_ENTERED",
        ),
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
    """An exact and *unique* provider match; prefixes are not proof."""
    expected_norm = expected_text.strip()
    if not expected_norm:
        return None
    matches = [post for post in api_posts
               if str(post.get("text", "")).strip() == expected_norm]
    return matches[0] if len(matches) == 1 else None


def _verified_provider_identity(post: dict, *, expected_text: str) -> bool:
    """An authenticated account readback must supply both ID and permalink."""
    import re

    if not expected_text.strip() or str(post.get("text", "")).strip() != expected_text.strip():
        return False
    if not re.fullmatch(r"[0-9]{2,30}", str(post.get("id", "")).strip()):
        return False
    try:
        parsed = urlsplit(str(post.get("permalink", "")).strip())
        port = parsed.port
    except ValueError:
        return False
    if (parsed.scheme != "https"
            or parsed.hostname not in {
                "threads.net", "www.threads.net",
                "threads.com", "www.threads.com",
            }
            or not re.fullmatch(r"/@[^/]+/post/[A-Za-z0-9_-]+/?", parsed.path)
            or parsed.username or parsed.password or port not in (None, 443)):
        return False
    return True


def _provider_timestamp_corresponds(queue_row: dict[str, Any], post: dict) -> bool:
    """The provider result must be from this exact failed save attempt."""
    started = str(queue_row.get("processed_at", "")).strip()
    provider = str(post.get("timestamp", "")).strip()
    if not started or not provider:
        return False
    try:
        a = datetime.fromisoformat(started.replace("Z", "+00:00"))
        b = datetime.fromisoformat(provider.replace("Z", "+00:00"))
    except ValueError:
        return False
    if a.tzinfo is None or b.tzinfo is None:
        return False
    return abs((a - b).total_seconds()) <= 900


def _write_recovery(
    client: SheetsClient,
    *,
    queue_row: dict[str, Any],
    social_derivative_id: str,
    text: str,
    external_post_id: str,
    post_url: str,
    dry_run: bool,
    provider_verified: bool = False,
) -> dict[str, Any]:
    # The legacy orphan tool must never fabricate a REAL posted result from
    # user-entered identity or an unauthenticated/partial Threads lookup.
    if not dry_run and str(queue_row.get("status", "")).strip().upper() not in {
        "POSTED_SAVE_FAILED", "POSTED_SAVE_UNVERIFIED", "PUBLISH_OUTCOME_UNVERIFIED",
    }:
        return {"status": "BLOCKED", "reason": "AMBIGUOUS_SAVE_FAILURE_STATE_REQUIRED"}
    if not dry_run and not provider_verified:
        return {"status": "BLOCKED", "reason": "LIVE_PROVIDER_PROOF_REQUIRED"}
    if not dry_run and not _verified_provider_identity(
        {"id": external_post_id, "permalink": post_url, "text": text},
        expected_text=text,
    ):
        return {"status": "BLOCKED", "reason": "LIVE_PROVIDER_IDENTITY_INVALID"}
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
        "verification_status": "LIVE_PROVIDER_MATCH_PENDING_SHEETS_READBACK",
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
    # Read back immediately before touching the source queue. A lost ACK must
    # not be turned into a second append or a silent success.
    matches = [row for row in _get_records(client, "posted_results")
               if str(row.get("result_id", "")) == result_id]
    if (len(matches) != 1
            or str(matches[0].get("queue_id", "")) != queue_id
            or str(matches[0].get("account_id", "")) != account_id
            or str(matches[0].get("external_post_id", "")) != external_post_id
            or str(matches[0].get("status", "")) != "RECOVERED"):
        return {
            "status": "PARTIAL_SAVE_UNVERIFIED_NO_RETRY",
            "reason": "POSTED_RESULT_READBACK_FAILED",
            "would_post": False,
        }

    updated = _update_row(client, "queue", "queue_id", queue_id, queue_update_fields)
    if not updated:
        return {
            "status": "PARTIAL_SAVE_UNVERIFIED_NO_RETRY",
            "reason": "QUEUE_UPDATE_UNVERIFIED",
            "would_post": False,
        }
    queue_matches = [row for row in _get_records(client, "queue")
                     if str(row.get("queue_id", "")) == queue_id]
    if (len(queue_matches) != 1
            or str(queue_matches[0].get("status", "")) != "POSTED"
            or str(queue_matches[0].get("account_id", "")) != account_id):
        return {
            "status": "PARTIAL_SAVE_UNVERIFIED_NO_RETRY",
            "reason": "QUEUE_READBACK_FAILED",
            "would_post": False,
        }

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



def _fetch_exact_threads_post(account_id: str, media_id: str) -> dict[str, Any]:
    """Read an existing Graph media ID with this account's token; never publish."""
    import re
    import requests

    if not re.fullmatch(r"[0-9]{2,30}", media_id):
        raise RuntimeError("saved_result_media_id_invalid")
    creds = resolve_credentials(account_id)
    token = str(creds.get("access_token") or "")
    user_id = str(creds.get("user_id") or "")
    if not token or not user_id:
        raise RuntimeError("saved_result_provider_credentials_missing")
    try:
        response = requests.get(
            f"https://graph.threads.net/v1.0/{media_id}",
            params={"fields": "id,text,timestamp,permalink"},
            headers={"Authorization": f"Bearer {token}"},
            timeout=30,
        )
        response.raise_for_status()
        payload = response.json()
    except Exception:
        # Provider response bodies and bearer secrets must not reach stdout.
        raise RuntimeError("saved_result_provider_readback_unavailable") from None
    if not isinstance(payload, dict):
        raise RuntimeError("saved_result_provider_response_invalid")
    return payload



def _write_verified_saved_result_queue_only(
    client: SheetsClient,
    *,
    queue_id: str,
    account_id: str,
    expected_text: str,
    expected_draft_id: str,
    result_id: str,
) -> bool:
    """Narrow exception for an independently proven *existing* external post.

    The ordinary queue writer intentionally prohibits any terminal-state
    transition. This private reconciliation writer must never be called before
    the saved POSTED result and the authenticated provider GET are proven
    identical. It changes precisely status/error/result_id, never immutable
    identity or posting fields; an ambiguous response is never retried.
    """
    if getattr(client, "dry_run", False):
        raise PermissionError("saved_queue_repair_dry_run_forbidden")
    ws = _ws(client, "queue")
    headers = _get_headers_with_retry(ws)
    required = {"queue_id", "account_id", "platform", "draft_id", "status",
                "result_id", "error", "public_post_text"}
    if len(headers) != len(set(headers)) or not required.issubset(headers):
        raise PermissionError("saved_queue_repair_schema_unverified")

    cells = client._call_with_rate_limit_retry(
        "findall:queue:saved_result_repair",
        lambda: ws.findall(queue_id, in_column=headers.index("queue_id") + 1),
    )
    exact = [cell for cell in cells if str(cell.value) == queue_id]
    if len(exact) != 1:
        raise PermissionError("saved_queue_repair_identity_ambiguous")
    rownum = exact[0].row
    before_values = client._call_with_rate_limit_retry(
        "row_values:queue:saved_result_repair:prewrite",
        lambda: ws.row_values(rownum),
    )
    before = dict(zip(headers, before_values))
    if (str(before.get("queue_id") or "") != queue_id
            or str(before.get("account_id") or "") != account_id
            or str(before.get("platform") or "").lower() != "threads"
            or str(before.get("status") or "").upper() != "POSTED_SAVE_FAILED"
            or str(before.get("draft_id") or "") != expected_draft_id
            or str(before.get("public_post_text") or "").strip() != expected_text
            or str(before.get("result_id") or "") not in {"", result_id}):
        raise PermissionError("saved_queue_repair_source_changed")

    # Queue-labelled updates use SheetsClient.sheets_write_once (no retries
    # after a possible remote commit). The old publisher guard is unchanged.
    client._batch_update_fields(
        ws, headers, rownum,
        {"status": "POSTED", "error": "", "result_id": result_id},
        label=f"queue:{queue_id}:saved_result_reconciliation",
    )
    after_values = client._call_with_rate_limit_retry(
        "row_values:queue:saved_result_repair:readback",
        lambda: ws.row_values(rownum),
    )
    after = dict(zip(headers, after_values))
    if (str(after.get("queue_id") or "") != queue_id
            or str(after.get("account_id") or "") != account_id
            or str(after.get("draft_id") or "") != expected_draft_id
            or str(after.get("public_post_text") or "").strip() != expected_text
            or str(after.get("status") or "").upper() != "POSTED"
            or str(after.get("result_id") or "") != result_id
            or str(after.get("error") or "").strip()):
        raise RuntimeError("saved_queue_repair_readback_unverified")
    return True


def reconcile_saved_result_queue(
    client: SheetsClient,
    queue: dict[str, Any],
    provider_post: dict[str, Any],
    *,
    apply: bool,
) -> dict[str, Any]:
    """Reconcile an already-saved result without creating or publishing a post.

    Both the existing Sheets read-after-write proof and an authenticated exact
    provider GET are required. This path NEVER appends posted_results or replays
    a publish request, even when a prior Sheets ACK was ambiguous.
    """
    queue_id = str(queue.get("queue_id", "")).strip()
    account = str(queue.get("account_id", "")).strip()
    if (not queue_id or account not in {"night_scout", "liver_manager"}
            or str(queue.get("status", "")).upper() != "POSTED_SAVE_FAILED"):
        return {"status": "BLOCKED", "reason": "EXACT_FAILED_QUEUE_REQUIRED"}
    existing = _get_records(client, "posted_results")
    matches = [row for row in existing if str(row.get("queue_id", "")) == queue_id]
    if len(matches) != 1:
        return {"status": "BLOCKED", "reason": "EXACT_EXISTING_RESULT_REQUIRED"}
    saved = matches[0]
    text = str(saved.get("posted_text", "")).strip()
    ext_id = str(saved.get("external_post_id", "")).strip()
    url = str(saved.get("post_url", "")).strip()
    if (str(saved.get("account_id", "")) != account
            or str(saved.get("platform", "")).lower() != "threads"
            or str(saved.get("status", "")).upper() != "POSTED"
            or str(saved.get("verification_status", "")).upper() != "READ_AFTER_WRITE_PASS"
            or str(saved.get("real_post", "")).lower() != "true"
            or not text or str(queue.get("public_post_text", "")).strip() != text
            or not str(saved.get("result_id", "")).strip()
            or not _verified_provider_identity(
                {"id": ext_id, "permalink": url, "text": text}, expected_text=text
            )):
        return {"status": "BLOCKED", "reason": "SAVED_RESULT_PROOF_INCOMPLETE"}
    if (str(queue.get("draft_id", "")).strip()
            and str(saved.get("draft_id", "")).strip() != str(queue.get("draft_id", "")).strip()):
        return {"status": "BLOCKED", "reason": "SAVED_RESULT_DRAFT_MISMATCH"}
    if sum(
        1 for row in existing
        if str(row.get("account_id", "")) == account
        and str(row.get("external_post_id", "")).strip() == ext_id
    ) != 1:
        return {"status": "BLOCKED", "reason": "SAVED_RESULT_EXTERNAL_ID_NOT_UNIQUE"}
    if (not isinstance(provider_post, dict)
            or str(provider_post.get("id", "")).strip() != ext_id
            or str(provider_post.get("permalink", "")).strip() != url
            or not _verified_provider_identity(provider_post, expected_text=text)
            or not _provider_timestamp_corresponds(queue, provider_post)):
        return {"status": "BLOCKED", "reason": "LIVE_PROVIDER_EXACT_MATCH_REQUIRED"}
    try:
        saved_at = datetime.fromisoformat(str(saved.get("posted_at", "")).replace("Z", "+00:00"))
        provider_at = datetime.fromisoformat(str(provider_post.get("timestamp", "")).replace("Z", "+00:00"))
        if (saved_at.tzinfo is None or provider_at.tzinfo is None
                or abs((saved_at - provider_at).total_seconds()) > 120):
            raise ValueError("timestamp_not_verified")
    except (ValueError, TypeError):
        return {"status": "BLOCKED", "reason": "LIVE_PROVIDER_POSTED_AT_MISMATCH"}

    result_id = str(saved["result_id"])
    plan = {
        "status": "PLAN_ONLY",
        "read_only": True,
        "queue_id": queue_id,
        "existing_result_id": result_id,
        "would_post": False,
        "would_append_posted_results": False,
        "metrics_reservation": "NOT_VERIFIED_BY_THIS_ACTION",
    }
    if not apply:
        return plan

    # Reload both tabs just before updating; fail closed if another operator
    # or workflow changed the source state while provider proof was fetched.
    current = [r for r in _get_records(client, "queue")
               if str(r.get("queue_id", "")) == queue_id]
    current_saved = [r for r in _get_records(client, "posted_results")
                     if str(r.get("queue_id", "")) == queue_id]
    if (len(current) != 1 or len(current_saved) != 1
            or str(current[0].get("status", "")).upper() != "POSTED_SAVE_FAILED"
            or str(current[0].get("account_id", "")) != account
            or str(current[0].get("public_post_text", "")).strip() != text
            or str(current_saved[0].get("result_id", "")) != result_id
            or str(current_saved[0].get("verification_status", "")).upper() != "READ_AFTER_WRITE_PASS"
            or str(current_saved[0].get("external_post_id", "")).strip() != ext_id):
        return {"status": "BLOCKED", "reason": "PREWRITE_SOURCE_CHANGED_NO_RETRY"}
    try:
        changed = _write_verified_saved_result_queue_only(
            client, queue_id=queue_id, account_id=account,
            expected_text=text, expected_draft_id=str(queue.get("draft_id") or ""),
            result_id=result_id,
        )
    except PermissionError:
        return {"status": "BLOCKED", "reason": "SAVED_RESULT_QUEUE_IDENTITY_CHANGED",
                "would_post": False}
    except Exception:
        # An accepted Sheets write can lose its acknowledgement. Never replay
        # the writer and never submit another Threads request.
        return {"status": "PARTIAL_SAVE_UNVERIFIED_NO_RETRY", "would_post": False}
    if not changed:
        return {"status": "PARTIAL_SAVE_UNVERIFIED_NO_RETRY", "would_post": False}
    after = [r for r in _get_records(client, "queue")
             if str(r.get("queue_id", "")) == queue_id]
    if (len(after) != 1 or str(after[0].get("status", "")).upper() != "POSTED"
            or str(after[0].get("result_id", "")) != result_id
            or str(after[0].get("account_id", "")) != account
            or str(after[0].get("error", "")).strip()):
        return {"status": "PARTIAL_SAVE_UNVERIFIED_NO_RETRY", "would_post": False}
    return {
        **plan, "status": "RECONCILED_QUEUE_ONLY", "read_only": False,
        "queue_readback_verified": True,
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
    parser.add_argument("--external-post-id", default="", help="API読取と一致を要求する任意の期待post ID")
    parser.add_argument("--post-url", default="", help="API読取と一致を要求する任意の期待投稿URL")
    parser.add_argument("--apply", action="store_true", help="Sheetsへの書き込みを実行する（省略時はdry-run）")
    parser.add_argument("--skip-api-lookup", action="store_true", help="非推奨: 実復旧は不可（読み取り専用保留）")
    parser.add_argument("--repair-existing-save", action="store_true")
    parser.add_argument("--reconcile-saved-result-queue", action="store_true",
                        help="Reconcile an already saved POSTED result to a failed queue without reposting")
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

    if args.reconcile_saved_result_queue:
        if args.repair_existing_save or args.skip_api_lookup or args.external_post_id or args.post_url:
            print("[BLOCKED] RECONCILE_REQUIRES_AUTHENTICATED_EXACT_PROVIDER_GET")
            return 2
        existing = [r for r in _get_records(client, "posted_results")
                    if str(r.get("queue_id", "")) == args.queue_id]
        if len(existing) != 1:
            print("[BLOCKED] EXACT_EXISTING_RESULT_REQUIRED")
            return 2
        try:
            provider = _fetch_exact_threads_post(args.account_id, str(existing[0].get("external_post_id", "")))
        except Exception:
            print("[BLOCKED] EXACT_PROVIDER_READBACK_FAILED")
            return 2
        outcome = reconcile_saved_result_queue(client, queue_row, provider, apply=args.apply)
        print(json.dumps(outcome, ensure_ascii=False, indent=2))
        return 0 if outcome["status"] in {"PLAN_ONLY", "RECONCILED_QUEUE_ONLY"} else 2

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

    # A supplied ID/URL is only a FILTER, never provider proof. Do not
    # claim a historical post exists just because an operator typed an ID.
    if args.apply and str(queue_row.get("status", "")).strip().upper() not in {
        "POSTED_SAVE_FAILED", "POSTED_SAVE_UNVERIFIED", "PUBLISH_OUTCOME_UNVERIFIED",
    }:
        print("[BLOCKED] AMBIGUOUS_SAVE_FAILURE_STATE_REQUIRED")
        return 2
    if args.skip_api_lookup:
        print("[BLOCKED] LIVE_PROVIDER_READBACK_REQUIRED; no recovery applied")
        return 2 if args.apply else 0

    print(f"  [LOOKUP] Threads API から読み取り専用で照合 (account_id={args.account_id})")
    try:
        api_posts = _fetch_recent_threads_posts(args.account_id, limit=25)
    except Exception as exc:
        # Never leak an HTTP client's token/URL/response into workflow logs.
        print(f"  [BLOCKED] LIVE_PROVIDER_READBACK_FAILED type={type(exc).__name__}")
        return 2 if args.apply else 0

    matched = _match_post_in_api_results(api_posts, text)
    if (matched is None or not _verified_provider_identity(matched, expected_text=text)):
        print("[BLOCKED] UNIQUE_EXACT_PROVIDER_POST_NOT_VERIFIED")
        return 2 if args.apply else 0
    if args.apply and not _provider_timestamp_corresponds(queue_row, matched):
        print("[BLOCKED] EXACT_PROVIDER_POST_TIMESTAMP_PROOF_REQUIRED")
        return 2
    external_post_id = str(matched["id"])
    post_url = str(matched["permalink"])
    if args.external_post_id and external_post_id != args.external_post_id:
        print("[BLOCKED] SUPPLIED_PROVIDER_ID_CONFLICT")
        return 2 if args.apply else 0
    if args.post_url and post_url != args.post_url:
        print("[BLOCKED] SUPPLIED_PROVIDER_PERMALINK_CONFLICT")
        return 2 if args.apply else 0
    print("  [MATCH] 認証済みThreads投稿が一意に一致（ID・本文・URL確認済み）")

    # Never trigger a second Threads POST. Any saved result is RECOVERED,
    # and only independently verified post/result readback can mark it final.
    outcome = _write_recovery(
        client,
        queue_row=queue_row,
        social_derivative_id=social_derivative_id,
        text=text,
        external_post_id=external_post_id,
        post_url=post_url,
        dry_run=dry_run,
        provider_verified=True,
    )
    print(json.dumps(outcome, ensure_ascii=False, indent=2))

    if dry_run:
        print("\n[DRY_RUN] 実際の書き込みは行いませんでした。--apply には認証済みAPI照合が必須です。")
    elif outcome.get("status") != "RECOVERED":
        print("[BLOCKED] PARTIAL_SAVE_UNVERIFIED_NO_RETRY: providerの再送は禁止")
        return 2
    else:
        print("[DONE] Threads再投稿なし・Sheets保存結果を再読込で確認")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
