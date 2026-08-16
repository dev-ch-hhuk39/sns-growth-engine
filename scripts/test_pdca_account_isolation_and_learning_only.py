#!/usr/bin/env python3
from __future__ import annotations

from generate_threads_ideas_from_references import (
    apply_measured_pdca_lineage,
    build_measured_pdca_inputs,
    build_measured_pdca_public_text,
    pdca_public_text_policy,
)
from public_post_quality import final_public_post_validator


def posted(result_id: str, account_id: str, text: str) -> dict[str, str]:
    return {
        "result_id": result_id,
        "account_id": account_id,
        "platform": "threads",
        "status": "POSTED",
        "posted_text": text,
        "content_route": "original_text",
        "generation_mode": "original_text",
    }


def measured(snapshot_id: str, result_id: str, account_id: str) -> dict[str, object]:
    return {
        "snapshot_id": snapshot_id,
        "result_id": result_id,
        "account_id": account_id,
        "platform": "threads",
        "metrics_status": "MEASURED",
        "views": 200,
        "likes": 20,
        "comments": 3,
        "reposts": 1,
        "quotes": 0,
        "collected_at": "2026-08-16T00:00:00+00:00",
    }


night_post = posted(
    "night_result",
    "night_scout",
    "体入では時給だけでなく、控除と手取りまで確認する。",
)
liver_post = posted(
    "liver_result",
    "liver_manager",
    "配信の最後に次回予告を置くと戻りやすい。",
)
posts, scores, meta = build_measured_pdca_inputs(
    measured_rows=[
        measured("night_ok", "night_result", "night_scout"),
        measured("wrong_account", "night_result", "liver_manager"),
        measured("liver_only", "liver_result", "liver_manager"),
    ],
    posted_results=[night_post, liver_post],
    account_id="night_scout",
)
assert posts and scores
assert set(meta) == {"night_result"}, meta
assert all(row["account_id"] == "night_scout" for row in posts)

night_text = build_measured_pdca_public_text(account_id="night_scout", meta=meta["night_result"])
liver_text = build_measured_pdca_public_text(
    account_id="liver_manager",
    meta={"source_text": liver_post["posted_text"]},
)
for account_id, text in (("night_scout", night_text), ("liver_manager", liver_text)):
    assert pdca_public_text_policy(text)["status"] == "PASS", text
    assert final_public_post_validator(text, account_id)["status"] == "PASS", text
    assert "前回の投稿" not in text
    assert "表示200" not in text

rows = {
    "drafts": [{"draft_id": "d1", "account_id": "night_scout"}],
    "social_derivatives": [{"draft_id": "d1", "account_id": "night_scout"}],
    "queue": [
        {
            "queue_id": "q1",
            "draft_id": "d1",
            "account_id": "night_scout",
            "source_id": "night_result",
            "public_post_text": night_text,
        }
    ],
}
grounded = apply_measured_pdca_lineage(
    rows,
    account_id="night_scout",
    source_meta=meta,
    top_n=1,
)
queue = grounded["queue"][0]
assert queue["public_post_text"] == night_text
assert queue["pdca_learning_account_id"] == "night_scout"
assert queue["pdca_learning_scope_id"] == "account:night_scout"
assert queue["transformation_type"] == "metrics_learned_original"
assert queue["source_credit"] == "internal_learning_only"
assert queue["metrics_disclosure_status"] == "PASS"

bad_rows = {
    "drafts": [],
    "social_derivatives": [],
    "queue": [{"account_id": "liver_manager", "source_id": "night_result"}],
}
try:
    apply_measured_pdca_lineage(
        bad_rows,
        account_id="night_scout",
        source_meta=meta,
        top_n=1,
    )
except ValueError as exc:
    assert str(exc) == "pdca_queue_account_mismatch"
else:
    raise AssertionError("cross-account PDCA queue was not blocked")

assert pdca_public_text_policy("前回の投稿は200表示でした。")["status"] == "BLOCKED"
print("PASS test_pdca_account_isolation_and_learning_only.py")
