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
  - 生成候補は WAITING_REVIEW（レビュー待ち）で書き込まれる。worker の
    ELIGIBLE_STATUSES（={READY}）には含まれないため、生成直後は投稿されない。
    投稿されるには次の多層ゲートを通る:
      1. 生成候補は WAITING_REVIEW であり worker 非対象（worker は READY のみ拾う）。
      2. 本 CLI も委譲先も投稿処理を一切呼ばない（生成専用）。
      3. READY への昇格は approve_queue.py による人間承認、または
         auto_approve_queue.py による validator PASS / text-only / cap/cooldown PASS の
         AUTO_READY のみ。生成系CLIは READY を直接書かない。
      4. 実投稿には別経路 worker の三重ゲート（--confirm-real-post かつ
         PUBLISH_ENABLED=true かつ ALLOW_REAL_THREADS_POST=true）が必要。
         scheduled applyではworkflow apply step内だけ true になり、ローカルdry-runでは false。
      5. beauty_account / X は本 CLI で BLOCKED。
  - READYゲート: approve_queue.py（人間）または auto_approve_queue.py（AUTO_READY）。
    worker が READY のみを eligible 扱いすることで、生成と投稿を分離する。
  - beauty_account は対象外。
"""
from __future__ import annotations

import argparse
import difflib
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from public_post_quality import (  # noqa: E402
    final_public_post_validator,
    generate_grounded_reader_facing_post,
    generate_reader_facing_post,
    reader_facing_template_count,
)

CLI_NAME = "generate_threads_ideas_from_references"
ALLOWED_ACCOUNTS = {"night_scout", "liver_manager"}
ALLOWED_PLATFORMS = {"threads"}
# worker が拾うステータス（process_threads_queue.py の ELIGIBLE_STATUSES と一致させる）。
# READY のみが worker 対象。生成候補(WAITING_REVIEW)は worker 非対象であることを明示する。
ELIGIBLE_STATUSES = {"READY"}
# 委譲先が実際に書き込む候補ステータス（両委譲先とも WAITING_REVIEW 固定）。
CANDIDATE_STATUS = "WAITING_REVIEW"
# 実投稿に必要なゲート（scheduled apply step内だけtrue化される）。
REAL_POST_GATES = ["--confirm-real-post", "PUBLISH_ENABLED=true", "ALLOW_REAL_THREADS_POST=true"]
# READYレビューゲート（WAITING_REVIEW → READY/REJECTED）。
READY_GATE = "approve_queue.py or auto_approve_queue.py"
SIMILARITY_BLOCK_THRESHOLD = 0.62
MAX_QUOTE_CHARS = 80
ALLOWED_TRANSFORMATION_TYPES = {
    "structure_reference",
    "hook_reference",
    "topic_reference",
    "owned_media_caption",
}

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


def _normalize_for_similarity(text: str) -> str:
    return re.sub(r"\s+", "", str(text or "").lower())


def original_text_similarity_guard(
    original_text: str,
    generated_text: str,
    *,
    threshold: float = SIMILARITY_BLOCK_THRESHOLD,
) -> dict[str, Any]:
    """Block drafts that are too close to reference wording."""
    original = _normalize_for_similarity(original_text)
    generated = _normalize_for_similarity(generated_text)
    if not original or not generated:
        return {"status": "PASS", "similarity": 0.0, "threshold": threshold, "reason": ""}
    similarity = difflib.SequenceMatcher(None, original, generated).ratio()
    copied_fragments = []
    matcher = difflib.SequenceMatcher(None, original, generated)
    for match in matcher.get_matching_blocks():
        if match.size >= 24:
            copied_fragments.append(original[match.a:match.a + match.size])
    copied_chars = sum(len(x) for x in copied_fragments)
    blocked = similarity >= threshold or copied_chars > MAX_QUOTE_CHARS
    return {
        "status": "BLOCKED" if blocked else "PASS",
        "similarity": round(similarity, 4),
        "threshold": threshold,
        "copied_chars": copied_chars,
        "quote_limit": MAX_QUOTE_CHARS,
        "reason": "generated_text is too similar to source text" if blocked else "",
    }


def direct_copy_block(original_text: str, generated_text: str) -> bool:
    return original_text_similarity_guard(original_text, generated_text)["status"] == "BLOCKED"


def build_rewritten_post_candidate(
    *,
    account_id: str,
    original_text: str,
    generated_text: str,
    transformation_type: str = "structure_reference",
    source_ref: str = "",
) -> dict[str, Any]:
    if transformation_type not in ALLOWED_TRANSFORMATION_TYPES:
        return {"status": "BLOCKED", "reason": "unsupported transformation_type", "transformation_type": transformation_type}
    guard = original_text_similarity_guard(original_text, generated_text)
    if guard["status"] == "BLOCKED":
        return {
            "status": "BLOCKED",
            "reason": guard["reason"],
            "transformation_type": transformation_type,
            "similarity_guard": guard,
            "generated_text": "",
            "candidate_status": "",
        }
    return {
        "status": "WAITING_REVIEW",
        "account_id": account_id,
        "generated_text": generated_text,
        "transformation_type": transformation_type,
        "similarity_guard": guard,
        "source_credit": "internal_reference_only",
        "source_ref": source_ref,
        "candidate_status": CANDIDATE_STATUS,
        "auto_publish": False,
    }


def build_thread_body(account_id: str, post: dict[str, Any], score: dict[str, Any], index: int) -> str:
    """Build reader-facing public text only.

    Reference details stay in internal generation metadata; public output must
    never mention source names, source platforms, scoring, or generation notes.
    """
    output = generate_grounded_reader_facing_post(
        account_id,
        private_signal=_post_text(post),
        index=index,
    )
    body = str(output["public_post_text"])
    validation = final_public_post_validator(body, account_id)
    if validation["status"] != "PASS":
        raise ValueError(f"public post template failed validation: {validation['blocked_reasons']}")
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
        candidate = build_rewritten_post_candidate(
            account_id=account_id,
            original_text=_post_text(post),
            generated_text=body,
            transformation_type="structure_reference",
            source_ref=ref_id,
        )
        if candidate["status"] == "BLOCKED":
            continue
        similarity_guard = candidate["similarity_guard"]
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
            "media_reuse_risk": "not_applicable",
            "transformation_type": "structure_reference",
            "source_credit": "internal_reference_only",
            "similarity_score": str(similarity_guard["similarity"]),
            "direct_copy_guard": similarity_guard["status"],
            "buzz_potential_score": str(score.get("total_score", "")),
            "conversion_potential_score": str(score.get("cta_score", "")),
            "confidence_level": "medium",
            "ai_publish_recommendation": CANDIDATE_STATUS,
            "notes": "Generated from REFERENCE_ONLY source metadata/scores. AUTO_READY or human review required. No third-party media reuse.",
        })
        derivatives.append({
            "derivative_id": derivative_id,
            "draft_id": draft_id,
            "account_id": account_id,
            "platform": "threads",
            "text": body,
            "hashtags": "",
            "status": CANDIDATE_STATUS,
            "reason": "AUTO_READY evaluation or human review required before READY.",
            "created_at": created,
            "char_count": str(len(body)),
            "text_policy_status": "PENDING",
            "media_strategy": "none",
            "transformation_type": "structure_reference",
            "source_credit": "internal_reference_only",
            "similarity_score": str(similarity_guard["similarity"]),
        })
        queues.append({
            "queue_id": queue_id,
            "draft_id": draft_id,
            "account_id": account_id,
            "target_account_id": account_id,
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
            "media_reuse_risk": "not_applicable",
            "public_post_text": body,
            "internal_analysis": f"Generated from reference_score_to_threads for source_id={post.get('source_id', '')}; public_post_text only is publishable.",
            "source_id": post.get("source_id", ""),
            "source_url": post.get("post_url", ""),
            "generated_by": CLI_NAME,
            "validator_status": "PENDING",
            "internal_leak_status": "",
            "account_fit_status": "",
            "rejected_reason": "",
            "blocked_reason": "",
            "updated_at": created,
        })
    for q in queues:
        assert q["status"] not in ELIGIBLE_STATUSES, "generated queue must not be worker-selectable"
        assert q["auto_publish"] == "false"
    return {"drafts": drafts, "social_derivatives": derivatives, "queue": queues}


def _fallback_template_index(offset: int, account_id: str) -> int:
    """Rotate safe original templates across daily runs without source data."""
    jst = timezone(timedelta(hours=9))
    now = datetime.now(timezone.utc).astimezone(jst)
    count = max(1, reader_facing_template_count(account_id))
    slot = now.hour * 4 + (now.minute // 15)
    return ((now.timetuple().tm_yday * 11 + slot + offset) % count) + 1


def build_fallback_generation_rows(*, account_id: str, top_n: int) -> dict[str, list[dict[str, Any]]]:
    """Build safe reader-facing original candidates when reference data is empty.

    This is the production recovery path for scheduled autonomous posting: it
    keeps the public text separate, validates it, writes WAITING_REVIEW only,
    and lets auto_approve_queue decide whether it may become READY.
    """
    created = now_iso()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    drafts: list[dict[str, Any]] = []
    derivatives: list[dict[str, Any]] = []
    queues: list[dict[str, Any]] = []
    for i in range(1, max(1, top_n) + 1):
        variant_index = _fallback_template_index(i, account_id)
        output = generate_reader_facing_post(account_id, index=variant_index)
        body = str(output["public_post_text"])
        validation = final_public_post_validator(body, account_id)
        if validation["status"] != "PASS":
            continue
        stable = _safe_id(f"{account_id}_fallback_{stamp}_{i}")
        draft_id = f"idea_{stable}"
        derivative_id = f"sd_{stable}_threads"
        queue_id = f"q_{stable}_threads"
        title = body.splitlines()[0][:80]
        drafts.append({
            "draft_id": draft_id,
            "created_at": created,
            "account_id": account_id,
            "title": title,
            "body_md": body,
            "content": body,
            "cta_text": "必要ならプロフィールから相談",
            "source_refs": "",
            "status": CANDIDATE_STATUS,
            "generation_model": CLI_NAME,
            "generation_mode": "safe_original_fallback_threads",
            "media_strategy": "none",
            "imitation_risk": "low",
            "media_reuse_risk": "not_applicable",
            "transformation_type": "original_hypothesis",
            "source_credit": "none",
            "similarity_score": "0.0",
            "direct_copy_guard": "PASS",
            "buzz_potential_score": "",
            "conversion_potential_score": "",
            "confidence_level": "medium",
            "ai_publish_recommendation": CANDIDATE_STATUS,
            "notes": "Safe original fallback for autonomous text-only posting when reference rows are empty.",
        })
        derivatives.append({
            "derivative_id": derivative_id,
            "draft_id": draft_id,
            "account_id": account_id,
            "platform": "threads",
            "text": body,
            "hashtags": "",
            "status": CANDIDATE_STATUS,
            "reason": "AUTO_READY evaluation required before posting.",
            "created_at": created,
            "char_count": str(len(body)),
            "text_policy_status": "PASS",
            "media_strategy": "none",
            "transformation_type": "original_hypothesis",
            "source_credit": "none",
            "similarity_score": "0.0",
        })
        queues.append({
            "queue_id": queue_id,
            "draft_id": draft_id,
            "account_id": account_id,
            "target_account_id": account_id,
            "platform": "threads",
            "scheduled_at": "",
            "priority": str(50 + i),
            "status": CANDIDATE_STATUS,
            "error": "",
            "created_at": created,
            "processed_at": "",
            "auto_publish": "false",
            "generation_mode": "safe_original_fallback_threads",
            "confidence_level": "medium",
            "ai_publish_recommendation": CANDIDATE_STATUS,
            "media_asset_id": "",
            "text_policy_status": "PASS",
            "rights_status": "not_required",
            "permission_status": "not_required",
            "rights_review_required": "false",
            "media_reuse_risk": "not_applicable",
            "public_post_text": body,
            "internal_analysis": "Safe original fallback; public_post_text only is publishable.",
            "source_id": "",
            "source_url": "",
            "generated_by": CLI_NAME,
            "validator_status": validation["status"],
            "internal_leak_status": validation["internal_leak_check"]["status"],
            "account_fit_status": validation["account_fit_check"]["status"],
            "public_post_quality_score": str(validation["public_post_quality_score"]),
            "reader_value_score": str(validation["reader_value_score"]),
            "naturalness_score": str(validation["naturalness_score"]),
            "cta_pressure_score": str(validation["cta_pressure_score"]),
            "rejected_reason": "",
            "blocked_reason": "",
            "updated_at": created,
        })
    return {"drafts": drafts, "social_derivatives": derivatives, "queue": queues}


LOCKED_GENERATION_STATUSES = {"READY", "PROCESSING", "POSTED", "MEDIA_READY"}


def _row_status(row: dict[str, Any]) -> str:
    return str(row.get("status") or row.get("ai_publish_recommendation") or "").strip().upper()


def _append_missing(client: Any, logical: str, key: str, rows: list[dict[str, Any]]) -> dict[str, int]:
    if not rows:
        return {"added": 0, "skipped": 0, "refreshed": 0}
    from gspread.utils import rowcol_to_a1

    ws = client._ws(logical)
    headers = ws.row_values(1)
    existing_rows: dict[str, tuple[int, dict[str, Any]]] = {}
    for row_number, existing in enumerate(ws.get_all_records(), start=2):
        existing_rows[str(existing.get(key, ""))] = (row_number, dict(existing))
    added = skipped = refreshed = 0
    update_ranges: list[dict[str, Any]] = []
    append_values: list[list[str]] = []
    for row in rows:
        row_key = str(row.get(key, ""))
        existing_info = existing_rows.get(row_key)
        if existing_info:
            row_number, existing = existing_info
            if _row_status(existing) in LOCKED_GENERATION_STATUSES:
                skipped += 1
                continue
            refreshed_row = {**existing, **row}
            update_ranges.append({
                "range": f"{rowcol_to_a1(row_number, 1)}:{rowcol_to_a1(row_number, len(headers))}",
                "values": [[str(refreshed_row.get(h, "")) for h in headers]],
            })
            existing_rows[row_key] = (row_number, refreshed_row)
            refreshed += 1
            continue
        append_values.append([str(row.get(h, "")) for h in headers])
        existing_rows[row_key] = (-1, dict(row))
        added += 1
    if update_ranges:
        ws.batch_update(update_ranges, value_input_option="USER_ENTERED")
    if append_values:
        ws.append_rows(append_values, value_input_option="USER_ENTERED")
    return {"added": added, "skipped": skipped, "refreshed": refreshed}


def run_reference_generation(account_id: str, top_n: int, *, apply: bool) -> dict[str, Any]:
    from config_loader import get_config
    from sheets_client import SheetsClient

    cfg = get_config()
    client = SheetsClient(cfg["sheet_id"], cfg["sa_dict"], dry_run=False)
    posts = [dict(r) for r in client._ws("source_account_posts").get_all_records() if str(r.get("account_id", "")) == account_id]
    scores = [dict(r) for r in client._ws("reference_post_scores").get_all_records() if str(r.get("account_id", "")) == account_id]
    rows = build_generation_rows(account_id=account_id, posts=posts, scores=scores, top_n=top_n)
    fallback_used = False
    if not rows["queue"]:
        rows = build_fallback_generation_rows(account_id=account_id, top_n=top_n)
        fallback_used = True
    summary = {
        "status": "PLAN_ONLY",
        "account_id": account_id,
        "source_posts": len(posts),
        "source_scores": len(scores),
        "candidate_count": len(rows["queue"]),
        "candidate_status": CANDIDATE_STATUS,
        "fallback_original_used": fallback_used,
        "queue_ids": [r["queue_id"] for r in rows["queue"]],
        "worker_selectable": False,
        "real_post_possible_now": False,
    }
    if not apply:
        return summary
    if not rows["queue"]:
        return {**summary, "status": "NO_DATA", "reason": "reference posts/scores and fallback candidates are missing"}
    ops = {
        "drafts": _append_missing(client, "drafts", "draft_id", rows["drafts"]),
        "social_derivatives": _append_missing(client, "social_derivatives", "derivative_id", rows["social_derivatives"]),
        "queue": _append_missing(client, "queue", "queue_id", rows["queue"]),
    }
    queue_writes = sum(int(ops["queue"].get(k, 0)) for k in ("added", "refreshed"))
    fallback_topup_used = False
    fallback_ops: dict[str, dict[str, int]] = {}
    if queue_writes == 0:
        fallback_rows = build_fallback_generation_rows(account_id=account_id, top_n=top_n)
        fallback_topup_used = bool(fallback_rows["queue"])
        fallback_ops = {
            "drafts": _append_missing(client, "drafts", "draft_id", fallback_rows["drafts"]),
            "social_derivatives": _append_missing(client, "social_derivatives", "derivative_id", fallback_rows["social_derivatives"]),
            "queue": _append_missing(client, "queue", "queue_id", fallback_rows["queue"]),
        }
    return {
        **summary,
        "status": "GENERATED",
        "fallback_topup_used": fallback_topup_used,
        "applied_operations": ops,
        "fallback_topup_operations": fallback_ops,
    }


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
            "ready_gate": f"{READY_GATE} (WAITING_REVIEW → READY/REJECTED)",
            "platform": args.platform,
        },
        "notes": (
            "本 CLI は生成専用（投稿しない）。候補は WAITING_REVIEW で書かれ worker 非対象。"
            "READY化は approve_queue.py または auto_approve_queue.py のみ。"
            "実投稿には別 worker の三重ゲートが必要。"
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
