#!/usr/bin/env python3
"""Offline, read-only media review workbench: no trusted authorization boundary.

This workbench joins Phase 5B-1/5B-2 sanitized reports with optional *offline*
queue/evidence snapshots. Even a matched snapshot cannot grant approval:
the trusted identity, live evidence repository, and transaction API remain
separate prerequisites. Never writes to Sheets, READY, or any publisher.
"""
from __future__ import annotations

import argparse
import html
import json
import os
import re
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from build_media_human_review_plan import MEDIA_SLOTS
from build_media_review_approval_receipts import (
    APPROVAL_EVIDENCE, CLIP_EVIDENCE, EVIDENCE_RE, QUEUE_ID_RE,
    ReviewContractError, _parse_instant, _sha256, _validate_history,
    _validate_plan,
)

MAX_JSON_BYTES = 2_000_000
MAX_QUEUE_ROWS = 200
MAX_EVIDENCE_ROWS = 400
MAX_SNAPSHOT_AGE = timedelta(minutes=30)
QUEUE_SCHEMA = "sns_media_queue_snapshot_v1"
EVIDENCE_SCHEMA = "sns_media_evidence_snapshot_v1"
BOARD_SCHEMA = "sns_media_review_workbench_v1"
PASS_RIGHTS = {"APPROVED", "ALLOWED", "AUTHORIZED", "GRANTED"}
SAFE_MEDIA_ID = re.compile(r"[A-Za-z0-9_.:-]{1,128}\Z")

BLOCKER_LABELS = {
    "exact_slot_candidate_missing": "対象枠に候補がありません",
    "queue_snapshot_missing": "最新の投稿キュー情報がありません",
    "queue_snapshot_stale": "投稿キュー情報が古くなっています",
    "queue_row_missing": "候補が投稿キューに存在しません",
    "queue_row_not_ready": "現在のキューはREADYではありません",
    "queue_account_or_slot_mismatch": "アカウント・枠が一致しません",
    "queue_media_asset_missing": "紐づくメディア素材IDがありません",
    "queue_rights_not_confirmed": "キューの素材権利が未確認です",
    "queue_permission_not_confirmed": "キューの利用許諾が未確認です",
    "queue_rights_review_pending": "権利レビューの保留フラグがあります",
    "queue_quality_gate_not_passed": "キューの品質・技術検査が未通過です",
    "review_plan_has_blockers": "一次レビューの未解決項目があります",
    "draft_approval_missing": "承認申請ドラフトがありません",
    "draft_decision_blocks": "却下・保留・取消の記録があります",
    "evidence_snapshot_missing": "証跡の照合用スナップショットがありません",
    "evidence_snapshot_stale": "証跡の照合データが古くなっています",
    "evidence_record_missing": "参照された証跡IDを確認できません",
    "evidence_record_mismatch": "証跡が別の素材・アカウント・用途に紐づいています",
    "evidence_not_verified": "証跡の確認または有効期限が不十分です",
    "rights_expired": "利用許諾が期限切れ、または未開始です",
    "authenticated_reviewer_missing": "認証済み担当者による正式承認が必要です",
}


def _read_json(path: Path) -> Any:
    try:
        if path.stat().st_size > MAX_JSON_BYTES:
            raise ReviewContractError("workbench_input_too_large")
        return json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError, UnicodeError) as exc:
        raise ReviewContractError("workbench_input_invalid") from exc


def _timestamp(value: Any) -> datetime:
    try:
        return _parse_instant(value)
    except (ReviewContractError, TypeError) as exc:
        raise ReviewContractError("snapshot_timestamp_invalid") from exc


def _snapshot_rows(
    document: Any, schema: str, key_name: str, limit: int, now: datetime,
) -> tuple[list[dict[str, Any]], bool]:
    if not isinstance(document, dict):
        raise ReviewContractError("snapshot_invalid")
    if document.get("schema_version") != schema or document.get("read_only") is not True:
        raise ReviewContractError("snapshot_not_read_only")
    rows = document.get(key_name)
    if not isinstance(rows, list) or len(rows) > limit or any(not isinstance(r, dict) for r in rows):
        raise ReviewContractError("snapshot_rows_invalid")
    captured = _timestamp(document.get("captured_at"))
    # A future-dated or old capture is never treated as current evidence.
    current = timedelta(0) <= now - captured <= MAX_SNAPSHOT_AGE
    return rows, current


def _queue_lookup(
    snapshot: Any, now: datetime,
) -> tuple[dict[str, dict[str, Any]], bool]:
    rows, fresh = _snapshot_rows(snapshot, QUEUE_SCHEMA, "rows", MAX_QUEUE_ROWS, now)
    by_id: dict[str, dict[str, Any]] = {}
    for row in rows:
        qid = row.get("queue_id")
        if not isinstance(qid, str) or not QUEUE_ID_RE.fullmatch(qid):
            raise ReviewContractError("snapshot_queue_id_invalid")
        if qid in by_id:
            raise ReviewContractError("snapshot_queue_duplicate")
        by_id[qid] = row
    return by_id, fresh


def _evidence_lookup(
    snapshot: Any, now: datetime,
) -> tuple[dict[str, dict[str, Any]], bool]:
    rows, fresh = _snapshot_rows(snapshot, EVIDENCE_SCHEMA, "records", MAX_EVIDENCE_ROWS, now)
    by_id: dict[str, dict[str, Any]] = {}
    for row in rows:
        eid = row.get("evidence_id")
        if not isinstance(eid, str) or not EVIDENCE_RE.fullmatch(eid):
            raise ReviewContractError("snapshot_evidence_id_invalid")
        if eid in by_id:
            raise ReviewContractError("snapshot_evidence_duplicate")
        by_id[eid] = row
    return by_id, fresh


def _candidate_queue_checks(
    account: str, slot: str, candidate_id: str, queue_rows: dict[str, dict[str, Any]],
) -> tuple[dict[str, Any] | None, set[str]]:
    row = queue_rows.get(candidate_id)
    if row is None:
        return None, {"queue_row_missing"}
    issues: set[str] = set()
    if row.get("account_id") != account or row.get("slot_id") != slot:
        issues.add("queue_account_or_slot_mismatch")
    if row.get("status") != "READY":
        issues.add("queue_row_not_ready")
    asset = row.get("media_asset_id")
    if not isinstance(asset, str) or not SAFE_MEDIA_ID.fullmatch(asset):
        issues.add("queue_media_asset_missing")
    for field, issue in (
        ("rights_status", "queue_rights_not_confirmed"),
        ("permission_status", "queue_permission_not_confirmed"),
    ):
        if str(row.get(field) or "").upper() not in PASS_RIGHTS:
            issues.add(issue)
    if row.get("rights_review_required") is not False:
        issues.add("queue_rights_review_pending")
    for field in ("validator_status", "internal_leak_status", "account_fit_status",
                  "alignment_status", "hybrid_ai_status"):
        if row.get(field) != "PASS":
            issues.add("queue_quality_gate_not_passed")
    return row, issues


def _evidence_checks(
    event: dict[str, Any],
    row: dict[str, Any],
    evidence: dict[str, dict[str, Any]],
    now: datetime,
) -> set[str]:
    issues: set[str] = set()
    account, slot, queue_id = event["account_id"], event["slot_id"], event["queue_id"]
    kinds = set(APPROVAL_EVIDENCE)
    if MEDIA_SLOTS[(account, slot)] == "approved_source_clip":
        kinds.update(CLIP_EVIDENCE)
    refs = event.get("evidence_ids")
    if not isinstance(refs, dict) or set(refs) != kinds:
        return {"evidence_record_missing"}
    try:
        if not (_timestamp(event["rights_valid_from"]) <= now
                < _timestamp(event["rights_expires_at"])):
            issues.add("rights_expired")
    except ReviewContractError:
        issues.add("rights_expired")
    for kind, ref in refs.items():
        if not isinstance(ref, str):
            issues.add("evidence_record_missing")
            continue
        record = evidence.get(ref)
        if not record:
            issues.add("evidence_record_missing")
            continue
        if (record.get("kind") != kind
                or record.get("account_id") != account
                or record.get("slot_id") != slot
                or record.get("queue_id") != queue_id
                or record.get("media_asset_id") != row.get("media_asset_id")
                or record.get("usage_scope") != "THREADS_ORGANIC_ONLY"):
            issues.add("evidence_record_mismatch")
        try:
            valid = (_timestamp(record.get("rights_valid_from")) <= now
                     < _timestamp(record.get("rights_expires_at")))
        except ReviewContractError:
            valid = False
        if record.get("verification_status") != "VERIFIED" or record.get("revoked") is not False or not valid:
            issues.add("evidence_not_verified")
    return issues


def build_workbench(
    plan: dict[str, Any],
    *,
    receipts: dict[str, Any] | None = None,
    queue_snapshot: dict[str, Any] | None = None,
    evidence_snapshot: dict[str, Any] | None = None,
    account_id: str = "all",
    as_of: datetime | None = None,
) -> dict[str, Any]:
    now = as_of or datetime.now(timezone.utc)
    if now.tzinfo is None or now.utcoffset() is None:
        raise ReviewContractError("workbench_clock_requires_timezone")
    now = now.astimezone(timezone.utc)
    if account_id not in {"all", "night_scout", "liver_manager"}:
        raise ReviewContractError("workbench_account_scope_invalid")
    choice_map = _validate_plan(plan)
    digest = _sha256(plan)
    history, history_head = _validate_history(receipts, digest, choice_map)
    if queue_snapshot is None:
        queues, queue_fresh = {}, False
    else:
        queues, queue_fresh = _queue_lookup(queue_snapshot, now)
    if evidence_snapshot is None:
        proofs, evidence_fresh = {}, False
    else:
        proofs, evidence_fresh = _evidence_lookup(evidence_snapshot, now)
    latest: dict[tuple[str, str, str], dict[str, Any]] = {}
    for event in history:
        latest[(event["account_id"], event["slot_id"], event["queue_id"])] = event
    items: list[dict[str, Any]] = []
    for (account, slot, qid), candidate in choice_map.items():
        if account_id != "all" and account_id != account:
            continue
        blockers: set[str] = set()
        if candidate.get("blockers"):
            blockers.add("review_plan_has_blockers")
        if not qid:
            blockers.add("exact_slot_candidate_missing")
        if queue_snapshot is None:
            blockers.add("queue_snapshot_missing")
        elif not queue_fresh:
            blockers.add("queue_snapshot_stale")
        row = None
        if qid and queue_snapshot is not None:
            row, queue_issues = _candidate_queue_checks(account, slot, qid, queues)
            blockers.update(queue_issues)
        event = latest.get((account, slot, qid))
        if event is None:
            blockers.add("draft_approval_missing")
        elif event["decision"] != "APPROVE":
            blockers.add("draft_decision_blocks")
        elif row is not None:
            if evidence_snapshot is None:
                blockers.add("evidence_snapshot_missing")
            elif not evidence_fresh:
                blockers.add("evidence_snapshot_stale")
            blockers.update(_evidence_checks(event, row, proofs, now))
        # An untrusted offline snapshot can never certify a human identity.
        blockers.add("authenticated_reviewer_missing")
        items.append({
            "account_id": account, "slot_id": slot, "post_type": MEDIA_SLOTS[(account, slot)],
            "queue_id": qid, "priority": candidate["priority"],
            "review_state": "BLOCKED" if len(blockers) > 1 else "AUTHENTICATION_REQUIRED",
            "action_required": sorted(blockers),
            "latest_draft_decision": event["decision"] if event else "NONE",
            "license_expiry_utc": event.get("rights_expires_at", "") if event else "",
            "canonical_ready_verified": False,
            "authenticated_approval": False, "publish_authorized": False,
        })
    items.sort(key=lambda row: (
        {"P1": 0, "P2": 1, "P3": 2}[row["priority"]],
        row["account_id"], row["slot_id"], row["queue_id"],
    ))
    return {
        "schema_version": BOARD_SCHEMA,
        "status": "READ_ONLY_REVIEW_WORKBENCH",
        "account_scope": account_id,
        "generated_at": now.isoformat(timespec="seconds"),
        "source_plan_sha256": digest,
        "source_receipts_head_sha256": history_head,
        "queue_snapshot_current": queue_fresh,
        "evidence_snapshot_current": evidence_fresh,
        "item_count": len(items),
        "items": items,
        "authenticated_approval": False, "ready_transitions_performed": False,
        "writes_performed": False, "publish_authorized": False,
    }


def render_html(board: dict[str, Any]) -> str:
    """Single-file workbench. No media URLs, APIs, forms, or external resources."""
    if board.get("schema_version") != BOARD_SCHEMA or board.get("publish_authorized") is not False:
        raise ReviewContractError("workbench_document_invalid")
    esc = lambda value: html.escape(str(value), quote=True)
    nonce = secrets.token_urlsafe(18)
    sections = []
    for item in board["items"]:
        blockers = "".join(
            "<li>" + esc(BLOCKER_LABELS.get(key, "確認が必要な項目があります")) + "</li>"
            for key in item["action_required"]
        )
        sections.append(
            '<article class="candidate" data-account="' + esc(item["account_id"])
            + '" data-priority="' + esc(item["priority"]) + '">'
            + '<div class="top"><span class="priority">' + esc(item["priority"]) + '</span>'
            + '<strong>' + esc(item["slot_id"]) + '</strong>'
            + '<span class="muted">' + esc(item["account_id"]) + '</span></div>'
            + '<p>候補ID: <code>' + esc(item["queue_id"] or "(候補なし)") + '</code></p>'
            + '<p>申請履歴: ' + esc(item["latest_draft_decision"]) + ' / 権利期限: '
            + esc(item["license_expiry_utc"] or "未登録") + '</p>'
            + '<details><summary>確認事項 ' + str(len(item["action_required"]))
            + '件</summary><ul>' + blockers + '</ul></details>'
            + '<p class="blocked">正式承認未確認・投稿不可</p></article>'
        )
    html_body = "\n".join(sections) or "<p>対象アカウントに候補がありません。</p>"
    return f"""<!doctype html>
<html lang="ja"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'nonce-{nonce}'; script-src 'nonce-{nonce}'; img-src 'none'; connect-src 'none'; form-action 'none'; base-uri 'none'">
<title>SNS Growth | メディア確認ボード</title>
<style nonce="{nonce}">
:root {{font-family:system-ui,-apple-system,sans-serif;color:#19233b;background:#f4f6fa}}
*{{box-sizing:border-box}} body{{margin:0}} header{{background:#13243d;color:white;padding:2rem max(1rem,calc((100vw - 1080px)/2))}}
header p{{color:#cdd9e9;max-width:48rem}} main{{max-width:1080px;margin:auto;padding:1.4rem 1rem 3rem}}
h1{{margin:.25rem 0}} .banner{{border-left:4px solid #b84f26;background:#fff9ec;padding:1rem;border-radius:.3rem;margin:1rem 0}}
.controls{{display:flex;gap:.8rem;flex-wrap:wrap;margin:1.4rem 0}} label{{display:grid;gap:.3rem;font-weight:600}}
select{{font:inherit;padding:.6rem;border:1px solid #bdc9d8;border-radius:.4rem;background:white}}
#cards{{display:grid;grid-template-columns:repeat(auto-fit,minmax(295px,1fr));gap:.85rem}}
.candidate{{background:white;padding:1rem;border:1px solid #dce2ec;border-radius:.65rem;box-shadow:0 2px 7px #10243d0a;overflow-wrap:anywhere}}
.top{{display:flex;align-items:center;gap:.55rem;flex-wrap:wrap}} .priority{{font-size:.76rem;background:#e9edf5;padding:.25rem .5rem;border-radius:50px}}
.muted{{color:#53647d;font-size:.86rem}} .blocked{{font-size:.85rem;color:#903315;font-weight:700}}
summary{{cursor:pointer;font-weight:600}} details{{margin-top:.8rem}} li{{margin:.35rem 0}} code{{font-size:.86rem}}
footer{{margin-top:2rem;color:#53647d;font-size:.85rem}}
@media(max-width:540px){{header{{padding:1.4rem 1rem}}#cards{{grid-template-columns:1fr}}}}
</style></head><body>
<header><p>SNS Growth Engine / Phase 5B-3</p><h1>メディア確認ボード</h1>
<p>権利・品質・証跡の確認専用です。オフライン資料による承認は無効です。READY変更と投稿は実行できません。</p></header>
<main><div class="banner" role="status"><strong>読み取り専用</strong>
<p>認証済み担当者と原本証跡の照合は未接続です。現時点ではどの候補も正式承認されません。</p></div>
<div class="controls"><label>アカウント<select id="account"><option value="all">すべて</option>
<option value="night_scout">night_scout</option><option value="liver_manager">liver_manager</option>
</select></label><label>優先度<select id="priority"><option value="all">すべて</option>
<option value="P1">P1 最優先</option><option value="P2">P2 要確認</option>
<option value="P3">P3 最終レビュー</option></select></label></div>
<p id="visible-count" aria-live="polite">{len(board["items"])}件を表示</p>
<div id="cards">{html_body}</div>
<footer>取得時刻: {esc(board["generated_at"])} / 監査照合ID:
<code>{esc(board["source_plan_sha256"][:16])}</code> / 外部通信・入力送信なし</footer></main>
<script nonce="{nonce}">
(() => {{
  const account = document.getElementById('account');
  const priority = document.getElementById('priority');
  const cards = Array.from(document.querySelectorAll('.candidate'));
  const count = document.getElementById('visible-count');
  const update = () => {{
    let shown = 0;
    for (const card of cards) {{
      const show = (account.value === 'all' || card.dataset.account === account.value)
        && (priority.value === 'all' || card.dataset.priority === priority.value);
      card.hidden = !show;
      if (show) shown++;
    }}
    count.textContent = shown + '件を表示';
  }};
  account.addEventListener('change', update);
  priority.addEventListener('change', update);
  update();
}})();
</script></body></html>
"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan-json", type=Path, required=True)
    parser.add_argument("--receipts-json", type=Path)
    parser.add_argument("--queue-snapshot-json", type=Path)
    parser.add_argument("--evidence-snapshot-json", type=Path)
    parser.add_argument("--account-id", choices=("all", "night_scout", "liver_manager"),
                        default="all")
    parser.add_argument("--output-html", type=Path, required=True)
    args = parser.parse_args()
    try:
        board = build_workbench(
            _read_json(args.plan_json),
            receipts=_read_json(args.receipts_json) if args.receipts_json else None,
            queue_snapshot=_read_json(args.queue_snapshot_json) if args.queue_snapshot_json else None,
            evidence_snapshot=_read_json(args.evidence_snapshot_json)
            if args.evidence_snapshot_json else None,
            account_id=args.account_id,
        )
        markup = render_html(board)
        descriptor = os.open(args.output_html, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(markup)
        print(json.dumps({
            "status": board["status"], "item_count": board["item_count"],
            "queue_snapshot_current": board["queue_snapshot_current"],
            "evidence_snapshot_current": board["evidence_snapshot_current"],
            "publish_authorized": False,
        }, ensure_ascii=False))
        return 0
    except (OSError, UnicodeError, json.JSONDecodeError, ReviewContractError):
        print("REVIEW_WORKBENCH_BLOCKED")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
