#!/usr/bin/env python3
"""Focused acceptance checks for the Media V1 Hard/Soft contract."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "src")]

from media_post_validator import validate_media_post  # noqa: E402
from publication_review_board import decision_for_row  # noqa: E402


TEXTS = {
    "night_scout": "店を選ぶ時は時給だけで決めず、客層や出勤ペースまで確認すると続けやすい。迷う条件を一つずつ整理しておこう。",
    "liver_manager": "配信の初見さんが入りやすい空気は、最初の一言で変わる。今話している内容を短く伝えるところから始めてみよう。",
    "beauty_account": "スキンケアって重ねるほど良い気がするけど、肌がゆらぐ日はシンプルにするのも大事かも🥺 今の肌に合わせて選んでみてね✨",
}


def plan(account_id: str) -> dict:
    return {
        "rights_status": "owned",
        "permission_status": "approved",
        "media_url": "https://res.cloudinary.example/video.mp4",
        "media_asset_id": f"asset_{account_id}",
        "platform": "threads",
        "account_id": account_id,
        "target_account_id": account_id,
        "content_type": "direct_reference_media",
        "media_type": "video",
        "media_origin": "direct_reference",
        "duration_seconds": 20,
        "aspect_ratio": "9:16",
        "public_post_text": TEXTS[account_id],
        "alignment_status": "BLOCKED",
        "final_alignment_score": 0,
        "main_claim_coverage": 0,
        "unsupported_claim_count": 3,
        "source_copy_similarity": 1,
        "recent_post_similarity": 1,
    }


checks: list[tuple[str, bool]] = []
for account_id in TEXTS:
    result = validate_media_post(plan(account_id))
    checks.append((f"{account_id} soft quality warnings do not block", result["status"] == "PASS"))
    checks.append((f"{account_id} warnings persist", result["soft_warning_count"] > 0))

rights = validate_media_post({**plan("night_scout"), "rights_status": "unknown"})
checks.append(("unknown rights hard block", "rights_status_not_approved" in rights["blocked_reasons"]))

permission = validate_media_post({**plan("night_scout"), "permission_status": "pending"})
checks.append(("missing permission hard block", "permission_status_not_approved" in permission["blocked_reasons"]))

isolation = validate_media_post({**plan("night_scout"), "target_account_id": "liver_manager"})
checks.append(("cross-account media hard block", "account_namespace_mismatch" in isolation["blocked_reasons"]))

broken = validate_media_post({
    **plan("liver_manager"),
    "enforce_video_stream_evidence": True,
    "video_stream_count": 0,
    "media_probe_status": "FAILED",
})
checks.append(("broken video hard block", "media_stream_evidence_missing" in broken["blocked_reasons"]))

leak = validate_media_post({**plan("liver_manager"), "public_post_text": "今回の切り口は source_url です"})
checks.append(("internal leak hard block", "internal_terms" in leak["blocked_reasons"]))

ready = {"status": "READY", "media_required": "true"}
feedback, fields = decision_for_row({"review_decision": "NG", "reviewer_note": "hook weak"}, ready, allow_media_posts=True)
checks.append(("post-hoc NG never retracts READY", feedback == "FEEDBACK_RECORDED" and "status" not in fields))
checks.append(("post-hoc NG persists feedback", fields.get("human_review_status") == "NG"))
checks.append(("UNREVIEWED never blocks", decision_for_row({}, ready, allow_media_posts=True)[0] == "SKIP"))

failed = [name for name, ok in checks if not ok]
for name, ok in checks:
    print(f"  {'PASS' if ok else 'FAIL'} {name}")
print(f"PASS: {len(checks) - len(failed)} / FAIL: {len(failed)}")
raise SystemExit(1 if failed else 0)
