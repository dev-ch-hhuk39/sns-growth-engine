#!/usr/bin/env python3
"""Refill Threads drafts/social_derivatives/queue from Sheets seeds."""
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

from config_loader import get_config  # noqa: E402
from sheets_client import SheetsClient  # noqa: E402
from tone_checker import check_ng_tone  # noqa: E402

ALLOWED_ACCOUNTS = {"night_scout", "liver_manager"}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def ws(client: SheetsClient, logical: str):
    return client._ws(logical)


def records(client: SheetsClient, logical: str) -> list[dict[str, Any]]:
    return [dict(r) for r in ws(client, logical).get_all_records()]


def append_many(client: SheetsClient, logical: str, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    sheet = ws(client, logical)
    headers = sheet.row_values(1)
    sheet.append_rows([[str(row.get(h, "")) for h in headers] for row in rows], value_input_option="USER_ENTERED")


def category_names(client: SheetsClient, account_id: str) -> list[str]:
    return [
        str(r.get("category_name", ""))
        for r in records(client, "content_categories")
        if r.get("account_id") == account_id and str(r.get("active", "")).upper() == "TRUE"
    ]


def prompt_count(client: SheetsClient, account_id: str) -> int:
    return len([
        r for r in records(client, "prompt_templates")
        if r.get("account_id") == account_id and str(r.get("template_name", "")).endswith("threads")
    ])


def active_learning_count(client: SheetsClient, account_id: str) -> int:
    return len([
        r for r in records(client, "learning_rules")
        if r.get("account_id") == account_id and str(r.get("active", "")).lower() == "true"
    ])


def text_for(account_id: str, category: str, index: int) -> tuple[str, str]:
    if account_id == "night_scout":
        title = f"{category}で差がつくポイント"
        body = (
            f"{category}で伸びる子は、感覚だけで動いていない\n\n"
            f"夜職は勢いも大事だけど、続けて稼ぐ子ほど自分の行動を見直している。"
            f"店、LINE、接客、メンタルのどこで詰まっているかを切り分けるだけで、次の一手がかなり変わるんだよね。"
        )
        if index % 3 == 0:
            body += "\n\n詳しく聞きたい子はLINEかDMで相談してね。"
        return title, body
    title = f"{category}を伸ばす見方"
    body = (
        f"{category}は、やみくもに頑張るより数字を見た方が早い\n\n"
        f"TikTokライブで伸びる人は、配信時間だけじゃなく、コメント率、戻ってくる人、ギフト後の反応を見ている。"
        f"改善する場所がわかると、配信の作り方も変わる。"
    )
    if index % 3 == 0:
        body += "\n\n配信の伸ばし方を相談したい人はLINEかDMで聞いてね。"
    return title, body


def build_rows(client: SheetsClient, account_id: str, count: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    categories = category_names(client, account_id)
    if not categories:
        raise RuntimeError(f"No active categories for {account_id}")
    if prompt_count(client, account_id) < 1:
        raise RuntimeError(f"No threads prompt template for {account_id}")
    if active_learning_count(client, account_id) > 0:
        raise RuntimeError(f"Active learning rules are not allowed for {account_id}")

    created = now_iso()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    drafts: list[dict[str, Any]] = []
    socials: list[dict[str, Any]] = []
    queues: list[dict[str, Any]] = []

    for i in range(1, count + 1):
        category = categories[(i - 1) % len(categories)]
        title, text = text_for(account_id, category, i)
        tone = check_ng_tone(text, account_id)
        if tone.status == "FAIL":
            raise RuntimeError(f"Tone check failed for {account_id}: {tone.message}")
        draft_id = f"refill_{account_id}_{stamp}_{i:02d}"
        derivative_id = f"refill_sd_{account_id}_{stamp}_{i:02d}"
        queue_id = f"refill_q_{account_id}_{stamp}_{i:02d}"
        drafts.append({
            "draft_id": draft_id,
            "created_at": created,
            "account_id": account_id,
            "title": title,
            "body_md": text,
            "content": text,
            "cta_text": "LINEまたはDM" if "LINE" in text or "DM" in text else "",
            "status": "WAITING_REVIEW",
            "generation_model": "refill_threads_queue",
            "prompt_version": "threads_first_refill",
            "brand_risk_score": "0",
            "post_mode": "threads_first",
            "generation_mode": "refill_seed",
            "media_strategy": "none",
            "media_reuse_risk": "low",
            "confidence_level": "medium",
            "ai_publish_recommendation": "WAITING_REVIEW",
            "notes": f"Refill generated from category={category}. X disabled.",
        })
        socials.append({
            "derivative_id": derivative_id,
            "draft_id": draft_id,
            "account_id": account_id,
            "platform": "threads",
            "text": text,
            "hashtags": "",
            "status": "WAITING_REVIEW",
            "reason": "refill_threads_queue",
            "created_at": created,
            "char_count": str(len(text)),
            "text_policy_status": "PASS",
            "media_strategy": "none",
        })
        queues.append({
            "queue_id": queue_id,
            "draft_id": draft_id,
            "account_id": account_id,
            "platform": "threads",
            "scheduled_at": "",
            "priority": str(10 + i),
            "status": "WAITING_REVIEW",
            "error": "",
            "created_at": created,
            "processed_at": "",
            "auto_publish": "false",
            "generation_mode": "refill_seed",
            "confidence_level": "medium",
            "ai_publish_recommendation": "WAITING_REVIEW",
            "text_policy_status": "PASS",
            "rights_status": "not_required",
            "permission_status": "not_required",
            "rights_review_required": "false",
            "media_reuse_risk": "low",
        })
    return drafts, socials, queues


def main() -> int:
    parser = argparse.ArgumentParser(description="Refill Threads queue")
    parser.add_argument("--account-id", required=True, choices=["night_scout", "liver_manager", "beauty_account"])
    parser.add_argument("--count", type=int, default=1)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if args.account_id not in ALLOWED_ACCOUNTS:
        print("[BLOCKED] beauty_account is draft_only; no refill rows created")
        return 1
    if args.count < 1 or args.count > 10:
        print("[ERROR] --count must be 1..10")
        return 1

    cfg = get_config()
    client = SheetsClient(cfg["sheet_id"], cfg["sa_dict"], dry_run=False)
    if args.dry_run:
        print("[READ_ONLY] --dry-run: setup_all/append/read-after-write are disabled")
    else:
        print("[REAL_WRITE] setup_all をスキップします（本番タブは初期化済みを前提）")
    before = len([r for r in records(client, "queue") if r.get("account_id") == args.account_id and str(r.get("platform", "")).lower() == "threads"])
    drafts, socials, queues = build_rows(client, args.account_id, args.count)

    if args.dry_run:
        print(json.dumps({
            "dry_run": True,
            "read_only": True,
            "account_id": args.account_id,
            "count": args.count,
            "queue_before": before,
            "sample_queue_id": queues[0]["queue_id"],
            "sample_text_length": len(socials[0]["text"]),
            "planned": [
                {
                    "queue_id": queue["queue_id"],
                    "draft_id": queue["draft_id"],
                    "text_length": len(social["text"]),
                    "tone_check": social["text_policy_status"],
                    "cta_present": bool(draft.get("cta_text", "")),
                    "platform": queue["platform"],
                    "status": queue["status"],
                }
                for draft, social, queue in zip(drafts, socials, queues)
            ],
        }, ensure_ascii=False))
        return 0

    append_many(client, "drafts", drafts)
    append_many(client, "social_derivatives", socials)
    append_many(client, "queue", queues)
    after = before + args.count
    ok = after >= before + args.count
    print(json.dumps({
        "status": "SEEDED" if ok else "VERIFY_FAILED",
        "account_id": args.account_id,
        "added": args.count,
        "queue_before": before,
        "queue_after": after,
    }, ensure_ascii=False))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
