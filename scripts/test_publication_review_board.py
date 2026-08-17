#!/usr/bin/env python3
"""Focused contract for the Sheets human-review board."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "src")]

from publication_review_board import decision_for_row, is_reviewable, review_row  # noqa: E402
from sheets_client import TAB_DEFINITIONS  # noqa: E402

text_queue = {
    "queue_id": "q_text", "account_id": "night_scout", "platform": "threads",
    "status": "WAITING_REVIEW", "public_post_text": "投稿本文です。", "validator_status": "PASS",
    "internal_leak_status": "PASS", "media_required": "false",
}
media_queue = {
    **text_queue, "queue_id": "q_media", "media_required": "true", "media_asset_id": "asset_1",
    "media_url": "https://res.cloudinary.example/asset_1.png", "media_type": "IMAGE", "media_status": "UPLOADED",
}
beauty_queue = {
    **text_queue,
    "queue_id": "q_beauty",
    "account_id": "beauty_account",
    "style_fingerprint_status": "VOICE_PERSONA_PASS",
    "style_fingerprint_score": "100",
    "semantic_voice_status": "PASS",
    "semantic_voice_score": "95",
}

row = review_row(text_queue, {"review_decision": "OK", "reviewer_note": "内容確認済み"})
checks = [
    ("review tab schema exists", "publication_review" in TAB_DEFINITIONS),
    ("queue records public text", row["public_post_text"] == "投稿本文です。"),
    ("sync preserves operator decision", row["review_decision"] == "OK" and row["reviewer_note"] == "内容確認済み"),
    ("beauty candidate is reviewable", is_reviewable(beauty_queue)),
    ("beauty remains human-gated", decision_for_row({}, beauty_queue, allow_media_posts=False)[0] == "SKIP"),
    ("explicit OK promotes beauty to READY", decision_for_row({"review_decision": "OK"}, beauty_queue, allow_media_posts=False)[0] == "READY"),
    ("Beauty without semantic voice cannot become READY", decision_for_row({"review_decision": "OK"}, {**beauty_queue, "semantic_voice_status": "BLOCKED"}, allow_media_posts=False)[0] == "BLOCKED_BEAUTY_VOICE"),
    ("OK text becomes READY only after validation", decision_for_row({"review_decision": "OK"}, text_queue, allow_media_posts=False)[0] == "READY"),
    ("OK prepared media becomes READY without publishing", decision_for_row({"review_decision": "OK"}, media_queue, allow_media_posts=False)[0] == "READY"),
    ("missing media stays pending", decision_for_row({"review_decision": "OK"}, {**media_queue, "media_url": ""}, allow_media_posts=True)[0] == "APPROVED_PENDING_MEDIA_GATE"),
    ("invalid text cannot be approved", decision_for_row({"review_decision": "OK"}, {**text_queue, "validator_status": "BLOCKED"}, allow_media_posts=False)[0] == "BLOCKED_VALIDATION"),
    ("NG rejects without publishing", decision_for_row({"review_decision": "NG"}, text_queue, allow_media_posts=False)[0] == "REJECTED"),
]
failed = [name for name, ok in checks if not ok]
for name, ok in checks:
    print(f"  {'PASS' if ok else 'FAIL'} {name}")
print(f"PASS: {len(checks) - len(failed)} / FAIL: {len(failed)}")
raise SystemExit(1 if failed else 0)
