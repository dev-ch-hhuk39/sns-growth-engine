#!/usr/bin/env python3
"""参考素材から Threads 投稿案を生成する標準 CLI（薄い入口）。

内部では既存スクリプトを再利用する:
  - --source references : generate_from_references.py（参考投稿から生成）
  - --source clips      : generate_from_video_clips.py（切り抜き候補から生成）

安全方針（プロジェクト CLAUDE.md 準拠）:
  - 既定はプランのみ（PLAN_ONLY）。委譲実行は --apply かつ --confirm-generate。
  - 投稿先は threads のみ（X は将来対応のみ・本 CLI からは生成しない）。
  - 本 CLI は「生成」だけを行う。委譲先（generate_from_references.py /
    generate_from_video_clips.py）は候補を作るだけで投稿 worker を呼ばない。
  - 生成候補は WAITING_REVIEW（レビュー待ち）で書き込まれる。これは worker の
    ELIGIBLE_STATUSES（={READY}）に含まれないため、worker は決して拾わない。
    自動投稿されない保証は次の多層で担保する:
      1. 生成候補は WAITING_REVIEW であり worker 非対象（worker は READY のみ拾う）。
      2. 本 CLI も委譲先も投稿処理を一切呼ばない（生成専用）。
      3. READY への昇格は approve_queue.py で人間が行う（生成系は READY を書かない）。
      4. 実投稿には別経路 worker の三重ゲート（--confirm-real-post かつ
         PUBLISH_ENABLED=true かつ ALLOW_REAL_THREADS_POST=true）が必要。
         これら 3 つは現状すべて禁止のため実投稿は不可能。
      5. beauty_account / X は本 CLI で BLOCKED。
  - 人間ゲート: approve_queue.py（WAITING_REVIEW → READY/REJECTED）。worker が
    READY のみを eligible 扱いすることで「項目ごとの人間 READY 昇格ゲート」を担保する。
  - beauty_account は対象外。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

CLI_NAME = "generate_threads_ideas_from_references"
ALLOWED_ACCOUNTS = {"night_scout", "liver_manager"}
ALLOWED_PLATFORMS = {"threads"}
# worker が拾うステータス（process_threads_queue.py の ELIGIBLE_STATUSES と一致させる）。
# READY のみが worker 対象。生成候補(WAITING_REVIEW)は worker 非対象であることを明示する。
ELIGIBLE_STATUSES = {"READY"}
# 委譲先が実際に書き込む候補ステータス（両委譲先とも WAITING_REVIEW 固定）。
CANDIDATE_STATUS = "WAITING_REVIEW"
# 実投稿に必要なゲート（現状すべて禁止 → 実投稿は不可能）。
REAL_POST_GATES = ["--confirm-real-post", "PUBLISH_ENABLED=true", "ALLOW_REAL_THREADS_POST=true"]
# 人間レビューゲート（WAITING_REVIEW → READY/REJECTED）。
HUMAN_GATE = "approve_queue.py"

DELEGATES = {
    "references": "scripts/generate_from_references.py",
    "clips": "scripts/generate_from_video_clips.py",
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_id(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_]+", "_", value).strip("_")[:90]


def _to_float(value: Any) -> float:
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return 0.0


def _post_text(post: dict[str, Any]) -> str:
    return str(post.get("post_text") or post.get("text") or post.get("content") or "").strip()


def build_thread_body(account_id: str, post: dict[str, Any], score: dict[str, Any], index: int) -> str:
    """Build a transformed Threads draft from a scored reference row.

    The body intentionally references only the theme/structure. It never copies
    third-party text or suggests media reuse.
    """
    theme = _post_text(post).splitlines()[0].replace("参考テーマ:", "").strip() or "参考テーマ"
    if account_id == "night_scout":
        hook = [
            "夜職でしんどくなる人ほど、最初に見るべきポイントがある。",
            "キャバで伸びる子は、気合いより先に環境を見ている。",
            "副収入を増やしたい時ほど、焦って店を選ばない方がいい。",
        ][(index - 1) % 3]
        body = (
            f"{hook}\n\n"
            f"今回の切り口は「{theme}」。\n"
            "そのまま真似るのではなく、働く前の不安、続かない理由、相談しやすさに分解して使う。\n\n"
            "強い求人っぽく見せるより、迷っている子が自分の状況を整理できる投稿にする。\n"
            "LINE/DMへの導線は最後に一言だけ。"
        )
    else:
        hook = [
            "配信が続く人は、才能より先に仕組みを作っている。",
            "ライバー候補者に必要なのは、盛る話より続け方の設計。",
            "ギフトを増やす前に、まずリスナーが戻る理由を作る。",
        ][(index - 1) % 3]
        body = (
            f"{hook}\n\n"
            f"今回の切り口は「{theme}」。\n"
            "元ネタは構造だけを参考にして、配信前の準備、継続の壁、相談できる安心感に変換する。\n\n"
            "事務所勧誘を強く出すより、候補者が一歩目を具体的に想像できる投稿にする。\n"
            "相談導線は押し売りにせず、必要な人だけが反応できる形にする。"
        )
    return body


def build_generation_rows(
    *,
    account_id: str,
    posts: list[dict[str, Any]],
    scores: list[dict[str, Any]],
    top_n: int,
) -> dict[str, list[dict[str, Any]]]:
    posts_by_id = {str(p.get("post_id", "")): p for p in posts}
    usable_scores = [
        s for s in scores
        if str(s.get("account_id", "")) == account_id
        and str(s.get("reference_post_id") or s.get("collected_post_id", "")) in posts_by_id
    ]
    usable_scores.sort(key=lambda s: _to_float(s.get("total_score")), reverse=True)
    created = now_iso()
    drafts: list[dict[str, Any]] = []
    derivatives: list[dict[str, Any]] = []
    queues: list[dict[str, Any]] = []
    for i, score in enumerate(usable_scores[:top_n], 1):
        ref_id = str(score.get("reference_post_id") or score.get("collected_post_id", ""))
        post = posts_by_id[ref_id]
        stable = _safe_id(f"{account_id}_{ref_id}")
        draft_id = f"idea_{stable}"
        derivative_id = f"sd_{stable}_threads"
        queue_id = f"q_{stable}_threads"
        body = build_thread_body(account_id, post, score, i)
        title = body.splitlines()[0][:80]
        drafts.append({
            "draft_id": draft_id,
            "created_at": created,
            "account_id": account_id,
            "title": title,
            "body_md": body,
            "content": body,
            "cta_text": "必要ならプロフィールから相談",
            "source_refs": ref_id,
            "status": CANDIDATE_STATUS,
            "generation_model": CLI_NAME,
            "generation_mode": "reference_score_to_threads",
            "media_strategy": "none",
            "imitation_risk": "low",
            "media_reuse_risk": "high",
            "buzz_potential_score": str(score.get("total_score", "")),
            "conversion_potential_score": str(score.get("cta_score", "")),
            "confidence_level": "medium",
            "ai_publish_recommendation": CANDIDATE_STATUS,
            "notes": "Generated from REFERENCE_ONLY source metadata/scores. Human review required. No third-party media reuse.",
        })
        derivatives.append({
            "derivative_id": derivative_id,
            "draft_id": draft_id,
            "account_id": account_id,
            "platform": "threads",
            "text": body,
            "hashtags": "",
            "status": CANDIDATE_STATUS,
            "reason": "Human review required before READY.",
            "created_at": created,
            "char_count": str(len(body)),
            "text_policy_status": "PENDING",
            "media_strategy": "none",
        })
        queues.append({
            "queue_id": queue_id,
            "draft_id": draft_id,
            "account_id": account_id,
            "platform": "threads",
            "scheduled_at": "",
            "priority": str(60 + i),
            "status": CANDIDATE_STATUS,
            "error": "",
            "created_at": created,
            "processed_at": "",
            "auto_publish": "false",
            "generation_mode": "reference_score_to_threads",
            "confidence_level": "medium",
            "ai_publish_recommendation": CANDIDATE_STATUS,
            "media_asset_id": "",
            "text_policy_status": "PENDING",
            "rights_status": "not_required",
            "permission_status": "not_required",
            "rights_review_required": "false",
            "media_reuse_risk": "high",
        })
    for q in queues:
        assert q["status"] not in ELIGIBLE_STATUSES, "generated queue must not be worker-selectable"
        assert q["auto_publish"] == "false"
    return {"drafts": drafts, "social_derivatives": derivatives, "queue": queues}


def _append_missing(client: Any, logical: str, key: str, rows: list[dict[str, Any]]) -> dict[str, int]:
    if not rows:
        return {"added": 0, "skipped": 0}
    ws = client._ws(logical)
    headers = ws.row_values(1)
    existing = {str(r.get(key, "")) for r in ws.get_all_records()}
    added = skipped = 0
    for row in rows:
        row_key = str(row.get(key, ""))
        if row_key in existing:
            skipped += 1
            continue
        ws.append_row([str(row.get(h, "")) for h in headers], value_input_option="USER_ENTERED")
        existing.add(row_key)
        added += 1
    return {"added": added, "skipped": skipped}


def run_reference_generation(account_id: str, top_n: int, *, apply: bool) -> dict[str, Any]:
    from config_loader import get_config
    from sheets_client import SheetsClient

    cfg = get_config()
    client = SheetsClient(cfg["sheet_id"], cfg["sa_dict"], dry_run=False)
    posts = [dict(r) for r in client._ws("source_account_posts").get_all_records() if str(r.get("account_id", "")) == account_id]
    scores = [dict(r) for r in client._ws("reference_post_scores").get_all_records() if str(r.get("account_id", "")) == account_id]
    rows = build_generation_rows(account_id=account_id, posts=posts, scores=scores, top_n=top_n)
    summary = {
        "status": "PLAN_ONLY",
        "account_id": account_id,
        "source_posts": len(posts),
        "source_scores": len(scores),
        "candidate_count": len(rows["queue"]),
        "candidate_status": CANDIDATE_STATUS,
        "queue_ids": [r["queue_id"] for r in rows["queue"]],
        "worker_selectable": False,
        "real_post_possible_now": False,
    }
    if not apply:
        return summary
    if not rows["queue"]:
        return {**summary, "status": "NO_DATA", "reason": "reference posts/scores are missing"}
    ops = {
        "drafts": _append_missing(client, "drafts", "draft_id", rows["drafts"]),
        "social_derivatives": _append_missing(client, "social_derivatives", "derivative_id", rows["social_derivatives"]),
        "queue": _append_missing(client, "queue", "queue_id", rows["queue"]),
    }
    return {**summary, "status": "GENERATED", "applied_operations": ops}


def build_plan(args: argparse.Namespace) -> dict[str, Any]:
    """委譲プランを純粋関数で組み立てる（Sheets/LLM 不要・テスト対象）。"""
    if args.account_id == "beauty_account":
        return {"status": "BLOCKED", "cli": CLI_NAME, "reason": "beauty_account は対象外（draft_only）"}
    if args.platform not in ALLOWED_PLATFORMS:
        return {"status": "BLOCKED", "cli": CLI_NAME, "reason": "platform は threads のみ（X は将来対応）"}
    if args.source not in DELEGATES:
        return {"status": "BLOCKED", "cli": CLI_NAME, "reason": "source は references / clips のみ"}

    apply = bool(args.apply)
    confirm = bool(args.confirm_generate)
    will_run = apply and confirm
    delegate = DELEGATES[args.source]

    if args.source == "references":
        argv = ["--account-id", args.account_id, "--platform", args.platform, "--top-n", str(args.top_n)]
        if not will_run:
            argv += ["--mock", "--dry-run"]
    else:  # clips
        argv = ["--account-id", args.account_id, "--limit", str(args.top_n)]
        if will_run:
            argv += ["--use-sheets"]
        else:
            argv += ["--mock-llm"]

    plan = {
        "status": "WILL_RUN" if will_run else "PLAN_ONLY",
        "cli": CLI_NAME,
        "account_id": args.account_id,
        "platform": args.platform,
        "source": args.source,
        "delegate_script": delegate,
        "delegate_argv": argv,
        "safety": {
            # 委譲先は WAITING_REVIEW で書く。これは worker eligible だが、
            # 本 CLI も委譲先も投稿処理を呼ばないため自動投稿はされない。
            "candidate_status": CANDIDATE_STATUS,
            "worker_selectable": CANDIDATE_STATUS in ELIGIBLE_STATUSES,
            # 本 CLI / 委譲先は生成専用で投稿経路を一切持たない（最重要不変条件）。
            "delegate_posts": False,
            # 実投稿は別 worker の三重ゲートが必要。現状すべて禁止 → 不可能。
            "real_post_requires": REAL_POST_GATES,
            "real_post_possible_now": False,
            "human_gate": f"{HUMAN_GATE} (WAITING_REVIEW → READY/REJECTED)",
            "platform": args.platform,
        },
        "notes": (
            "本 CLI は生成専用（投稿しない）。候補は WAITING_REVIEW で書かれ worker 非対象。"
            "実投稿には別 worker の三重ゲート（全禁止）が必要なため自動投稿されない。"
            "threads のみ。実行は --apply --confirm-generate。"
        ),
    }
    # 最重要不変条件: 本 CLI は投稿せず生成のみ（委譲先も投稿経路を持たない）。
    assert plan["safety"]["delegate_posts"] is False
    assert plan["safety"]["real_post_possible_now"] is False
    return plan


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="generate Threads ideas from references (thin wrapper, gated)")
    parser.add_argument("--account-id", required=True, choices=["night_scout", "liver_manager", "beauty_account"])
    parser.add_argument("--platform", default="threads")
    parser.add_argument("--source", default="references", choices=["references", "clips"])
    parser.add_argument("--top-n", type=int, default=3)
    parser.add_argument("--dry-run", action="store_true", help="explicit PLAN_ONLY mode (default unless --apply)")
    parser.add_argument("--apply", action="store_true", help="run delegate (needs --confirm-generate)")
    parser.add_argument("--confirm-generate", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    plan = build_plan(args)
    print(json.dumps(plan, ensure_ascii=False, indent=2))
    if plan["status"] == "BLOCKED":
        return 1
    if plan["status"] == "PLAN_ONLY" and args.dry_run and plan["source"] == "references":
        result = run_reference_generation(plan["account_id"], args.top_n, apply=False)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    if plan["status"] != "WILL_RUN":
        return 0
    if plan["source"] == "references":
        result = run_reference_generation(plan["account_id"], args.top_n, apply=True)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["status"] in {"GENERATED", "NO_DATA"} else 1
    # Clip generation remains delegated; it does not post.
    import subprocess
    cmd = [sys.executable, str(ROOT / plan["delegate_script"]), *plan["delegate_argv"]]
    return subprocess.run(cmd, cwd=str(ROOT)).returncode


if __name__ == "__main__":
    raise SystemExit(main())
