#!/usr/bin/env python3
"""Generate next-queue candidates from posted_results metrics (gated, never auto-posts).

posted_results の実測メトリクス（views/likes/comments）から ER を計算してランキングし、
上位の傾向を踏まえた次回投稿候補を作る。生成物は人手レビュー前提で、worker が拾わない
ステータスで保存する。

安全方針（プロジェクト CLAUDE.md 準拠）:
  - 生成 queue 行の status は ELIGIBLE_STATUSES（={READY}）に含めない。
    既定で "DRAFT" を使い、process_threads_queue.py が絶対に自動投稿しないようにする。
  - status を POSTED にしない。posted_results に本番結果を書かない。
  - 既定は計画のみ（PLAN_ONLY）。実書き込みは --apply かつ --confirm-generate の両方が必要。
  - beauty_account は対象外（draft_only）。x は対象外（threads のみ）。
  - source priority / learning_rules.active は一切変更しない。
  - 改善提案は status=WAITING_REVIEW で auto_apply=false。prompt/code は書き換えない。
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

# worker が投稿対象とするステータス（process_threads_queue.py と一致させる）= READY のみ。
# 生成候補はここに含めてはならない（既定 DRAFT）。
ELIGIBLE_STATUSES = {"READY"}
# 生成候補に付与する非投稿ステータス（worker が拾わない）。
NON_POSTABLE_STATUS = "DRAFT"

ALLOWED_ACCOUNTS = {"night_scout", "liver_manager"}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def compute_engagement_rate(views: int, likes: int, comments: int) -> float:
    """ER = (likes + comments) / views。views<=0 なら 0。純粋関数。"""
    if views <= 0:
        return 0.0
    return round((likes + comments) / views, 4)


def _to_int(value: Any) -> int:
    try:
        return int(str(value or "0").strip() or "0")
    except (TypeError, ValueError):
        return 0


def rank_results_by_engagement(
    posted_results: list[dict[str, Any]], account_id: str
) -> list[dict[str, Any]]:
    """measured な posted_results を ER 降順で並べて返す（純粋関数）。

    - account_id 一致のみ対象（空 account_id は許容）。
    - threads のみ対象（x は除外）。
    - metrics_status が MEASURED の行のみ（未計測は次回設計の根拠にしない）。
    """
    ranked: list[dict[str, Any]] = []
    for r in posted_results:
        if str(r.get("account_id", "")) not in ("", account_id):
            continue
        if str(r.get("platform", "threads")).lower() not in ("", "threads"):
            continue
        if str(r.get("metrics_status", "")).strip().upper() != "MEASURED":
            continue
        views = _to_int(r.get("views"))
        likes = _to_int(r.get("likes"))
        comments = _to_int(r.get("comments"))
        er = compute_engagement_rate(views, likes, comments)
        ranked.append({
            "result_id": str(r.get("result_id", "")),
            "content_type": str(r.get("content_type", "") or r.get("category", "")),
            "views": views,
            "likes": likes,
            "comments": comments,
            "er": er,
        })
    ranked.sort(key=lambda x: (x["er"], x["views"]), reverse=True)
    return ranked


def build_next_queue_candidates(
    ranked: list[dict[str, Any]], account_id: str, count: int, stamp: str
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    """上位傾向から次回候補 drafts/queue 行と改善提案を組み立てる（純粋関数）。

    生成 queue 行は status=NON_POSTABLE_STATUS（worker 非対象）で、媒体は付けない。
    """
    top = ranked[:count] if ranked else []
    created = now_iso()
    drafts: list[dict[str, Any]] = []
    queues: list[dict[str, Any]] = []

    for i, src in enumerate(top, 1):
        ctype = src.get("content_type") or "engagement"
        title = f"[次回候補] 高ER傾向 {ctype} の継続展開"
        body = (
            f"前回 ER {src['er']} を記録した「{ctype}」の切り口を、別角度で展開する案。\n\n"
            f"数字が出た理由を一段深掘りして、同じテーマで読者の次の疑問に答える構成にする。"
        )
        draft_id = f"nextq_{account_id}_{stamp}_{i:02d}"
        queue_id = f"nextq_q_{account_id}_{stamp}_{i:02d}"
        drafts.append({
            "draft_id": draft_id,
            "created_at": created,
            "account_id": account_id,
            "title": title,
            "body_md": body,
            "content": body,
            "status": "WAITING_REVIEW",  # drafts は人手レビュー（投稿は別工程）
            "generation_model": "generate_next_queue_from_metrics",
            "generation_mode": "metrics_driven_candidate",
            "media_strategy": "none",
            "media_reuse_risk": "low",
            "ai_publish_recommendation": "WAITING_REVIEW",
            "notes": f"Derived from result_id={src['result_id']} er={src['er']}. Human review required. X disabled.",
        })
        queues.append({
            "queue_id": queue_id,
            "draft_id": draft_id,
            "account_id": account_id,
            "platform": "threads",
            "scheduled_at": "",
            "priority": str(50 + i),
            "status": NON_POSTABLE_STATUS,  # worker 非対象（ELIGIBLE_STATUSES に含めない）
            "error": "",
            "created_at": created,
            "processed_at": "",
            "auto_publish": "false",
            "generation_mode": "metrics_driven_candidate",
            "confidence_level": "low",
            "ai_publish_recommendation": "WAITING_REVIEW",
            "text_policy_status": "PENDING",
            "rights_status": "not_required",
            "permission_status": "not_required",
            "rights_review_required": "false",
            "media_reuse_risk": "low",
        })

    # 生成ステータスが投稿対象に紛れていないことを保証する。
    for q in queues:
        assert q["status"] not in ELIGIBLE_STATUSES, "generated candidate must not be postable"

    suggestion = {
        "suggestion_id": f"sug_nextq_{account_id}_{stamp}",
        "account_id": account_id,
        "created_at": created,
        "source": "generate_next_queue_from_metrics",
        "suggestion_type": "strategy_review",
        "target_template": "",
        "current_behavior": "Next-queue candidates generated from measured metrics.",
        "suggested_change": "Review candidates and ER ranking before promoting to postable status.",
        "reason": f"top_er={top[0]['er'] if top else 'n/a'}; ranked={len(ranked)}",
        "expected_impact": "Human-reviewed PDCA only.",
        "priority": "medium",
        "status": "WAITING_REVIEW",
        "reviewed_by": "",
        "reviewed_at": "",
        "notes": "auto_apply=false; learning_rules remain inactive; source priority unchanged.",
    }
    return drafts, queues, suggestion


def _load_posted_results(input_json: str | None, read_sheets: bool, account_id: str):
    if input_json:
        with open(input_json, encoding="utf-8") as f:
            data = json.load(f)
        return None, data.get("posted_results", [])
    if read_sheets:
        from config_loader import get_config
        from sheets_client import SheetsClient
        cfg = get_config()
        client = SheetsClient(cfg["sheet_id"], cfg["sa_dict"], dry_run=not read_sheets)
        rows = [dict(r) for r in client._ws("posted_results").get_all_records()]
        return client, rows
    return None, []


def _append_many(client, logical: str, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    sheet = client._ws(logical)
    headers = sheet.row_values(1)
    sheet.append_rows(
        [[str(row.get(h, "")) for h in headers] for row in rows],
        value_input_option="USER_ENTERED",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="generate next-queue candidates from metrics (gated)")
    parser.add_argument("--account-id", required=True, choices=["night_scout", "liver_manager", "beauty_account"])
    parser.add_argument("--count", type=int, default=1)
    parser.add_argument("--input-json", help='{"posted_results":[...]} for offline planning/testing')
    parser.add_argument("--dry-run", action="store_true", help="explicit PLAN_ONLY mode; reads Sheets without writing")
    parser.add_argument("--apply", action="store_true", help="write candidates (needs --confirm-generate)")
    parser.add_argument("--confirm-generate", action="store_true", help="explicit confirmation for real write")
    parser.add_argument("--use-sheets", action="store_true", help="Accepted for production runbook compatibility")
    args = parser.parse_args()

    if args.account_id == "beauty_account":
        print(json.dumps({"status": "BLOCKED", "reason": "beauty_account は draft_only。対象外"}, ensure_ascii=False))
        return 1
    if args.count < 1 or args.count > 10:
        print(json.dumps({"status": "BLOCKED", "reason": "--count must be 1..10"}, ensure_ascii=False))
        return 1

    client, posted = _load_posted_results(args.input_json, args.apply or args.dry_run, args.account_id)
    ranked = rank_results_by_engagement(posted, args.account_id)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    drafts, queues, suggestion = build_next_queue_candidates(ranked, args.account_id, args.count, stamp)

    if not args.apply:
        print(json.dumps({
            "status": "PLAN_ONLY",
            "account_id": args.account_id,
            "measured_count": len(ranked),
            "candidate_count": len(queues),
            "candidate_status": NON_POSTABLE_STATUS,
            "top_er": ranked[0]["er"] if ranked else None,
            "queue_ids": [q["queue_id"] for q in queues],
            "notes": "書き込み未実行。実生成は --apply --confirm-generate。生成 status は worker 非対象。",
        }, ensure_ascii=False, indent=2))
        return 0

    if not args.confirm_generate:
        print(json.dumps({"status": "BLOCKED", "reason": "--apply には --confirm-generate が必要",
                          "would_create": [q["queue_id"] for q in queues]}, ensure_ascii=False))
        return 1
    if client is None:
        print(json.dumps({"status": "BLOCKED", "reason": "--apply は本番 Sheets 用です（--input-json と併用不可）"}, ensure_ascii=False))
        return 1
    if not queues:
        print(json.dumps({"status": "NO_DATA", "reason": "MEASURED な posted_results が無く候補を作れません"}, ensure_ascii=False))
        return 1

    _append_many(client, "drafts", drafts)
    _append_many(client, "queue", queues)
    _append_many(client, "prompt_improvement_suggestions", [suggestion])
    print(json.dumps({
        "status": "GENERATED",
        "account_id": args.account_id,
        "candidate_count": len(queues),
        "candidate_status": NON_POSTABLE_STATUS,
        "queue_ids": [q["queue_id"] for q in queues],
        "suggestion_id": suggestion["suggestion_id"],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
