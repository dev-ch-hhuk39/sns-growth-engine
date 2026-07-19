#!/usr/bin/env python3
"""A rejected direct-media caption must not consume the whole slot."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "src")]

import run_direct_reference_media_pipeline as pipeline


GOOD_TEXT = """夜職で店を選ぶとき、時給だけで決めると続かないことがあります。

客層、出勤ペース、ノルマ、担当への相談しやすさまで確認して、自分が無理なく続けられる環境かを見ることが大切です。

条件を比べる前に、譲れないことを三つだけ整理しておくと判断しやすくなります。"""


def post(post_id: str) -> dict:
    return {
        "source_post_id": post_id,
        "source_id": "src_test",
        "target_account_id": "night_scout",
        "platform": "threads",
        "profile_url": "https://www.threads.com/@approved",
        "canonical_post_url": f"https://www.threads.com/@approved/post/{post_id}",
        "external_post_id": post_id,
        "original_post_text": "店選びでは条件だけでなく相性と相談しやすさを確認する。",
        "published_at": "2026-07-19T00:00:00+00:00",
        "rights_status": "approved_creator_clip",
        "permission_status": "approved",
        "content_hash": f"hash_{post_id}",
    }


def media(post_id: str) -> dict:
    return {
        "source_post_media_id": f"spm_{post_id}",
        "source_post_id": post_id,
        "media_asset_id": f"asset_{post_id}",
        "media_index": "0",
        "media_type": "image",
        "original_media_url": f"https://cdn.example/{post_id}.jpg",
        "storage_url": f"https://res.cloudinary.com/demo/{post_id}.jpg",
        "cloudinary_status": "UPLOADED",
        "rights_status": "approved_creator_clip",
        "permission_status": "approved",
        "media_understanding": {
            "status": "PASS",
            "visual_summary": "店選びの判断項目をまとめた画像",
            "visible_text": "客層 出勤ペース ノルマ 相談しやすさ",
        },
    }


class CaptionService:
    def generate(self, bundle, **_kwargs):
        if bundle.source_post_id == "bad":
            return {
                "status": "BLOCKED",
                "public_post_text": "",
                "blocked_reasons": ["provider_rejected_candidate"],
                "semantic_alignment": {"status": "BLOCKED"},
            }
        return {
            "status": "PASS",
            "public_post_text": GOOD_TEXT,
            "internal_analysis": {"topic": "店選び"},
            "claim_support": [{"claim": "店選び", "evidence": "source"}],
            "blocked_reasons": [],
            "provider_name": "fixture",
            "provider_version": "1",
            "semantic_alignment": {
                "status": "PASS",
                "final_alignment_score": 0.90,
                "main_claim_coverage": 0.90,
                "unsupported_claim_count": 0,
                "source_copy_similarity": 0.20,
                "recent_post_similarity": 0.10,
            },
        }


original_records = pipeline._records
original_candidates = pipeline.select_direct_candidates
try:
    pipeline._records = lambda _client, logical: []
    pipeline.select_direct_candidates = lambda _client, _account: ([
        (post("bad"), {**media("bad"), "carousel_media": [media("bad")]}, {}),
        (post("good"), {**media("good"), "carousel_media": [media("good")]}, {}),
    ], [])
    plan = pipeline.build_plan(
        "night_scout",
        "ns_1800_direct_media",
        object(),
        apply=False,
        caption_service=CaptionService(),
    )
finally:
    pipeline._records = original_records
    pipeline.select_direct_candidates = original_candidates

checks = [
    ("second candidate selected", plan.get("source_post_id") == "good"),
    ("first candidate recorded as skipped", plan.get("candidate_attempt_count") == 2),
    ("plan remains postable", plan.get("status") == "PLAN_ONLY"),
    ("semantic alignment passes", plan.get("semantic_alignment", {}).get("status") == "PASS"),
]
for name, passed in checks:
    print(f"  {'PASS' if passed else 'FAIL'} {name}")
failed = [name for name, passed in checks if not passed]
print(f"PASS: {len(checks) - len(failed)} / FAIL: {len(failed)}")
raise SystemExit(1 if failed else 0)
