#!/usr/bin/env python3
"""Saved clip dispatch claims first and treats POSTED_SAVE_FAILED as terminal."""
import run_media_production_pipeline as production


FINAL_TEXT = (
    "配信で初見さんが入りやすい空気を作るには、"
    "入室に気づいたら今話している内容を一言共有して、"
    "答えやすい質問を置くことが大事です。"
    "会話への入口を用意すると、コメントのきっかけを作りやすくなります。"
)


class Client:
    def __init__(self):
        self.clip_update = {}

    def update_video_clip_candidate(
        self,
        _clip_id,
        **fields,
    ):
        self.clip_update = fields

    def save_source_video(self, _row):
        return None


plan = {
    "account_id": "liver_manager",
    "slot_id": "lm_1800_clip_media",
    "selected_clip": {
        "clip_candidate_id": "clip_1",
        "source_video_id": "sv_1",
        # This stale candidate text must not be reused.
        "public_post_text": "OLD_CANDIDATE_TEXT",
        "rights_status": "approved_creator_clip",
        "permission_status": "approved",
        "transcript_grounded": "true",
        "transcript_excerpt": (
            "初見が来た時は、今話している内容を伝えて、"
            "答えやすい質問を置く。"
        ),
        "start_seconds": "10",
        "end_seconds": "30",
        "alignment_status": "PASS",
        "final_alignment_score": "0.95",
        "main_claim_coverage": "1.0",
        "unsupported_claim_count": "0",
        "source_copy_similarity": "0.20",
        "recent_post_similarity": "0.10",
    },
    "selected_source_video": {
        "source_video_id": "sv_1",
        "source_id": "source_1",
        "platform": "youtube",
        "canonical_video_url": (
            "https://www.youtube.com/watch?v=abcdefghijk"
        ),
        "title": "初見が入りやすい配信",
        "description_preview": (
            "初見への声かけと質問の置き方を説明する"
        ),
    },
    "selected_media_asset": {
        "media_asset_id": "asset_1",
        "storage_url": (
            "https://res.cloudinary.com/"
            "demo/video/upload/clip.mp4"
        ),
        "upload_status": "UPLOADED",
        "rights_status": "approved_creator_clip",
        "permission_status": "approved",
        "duration_seconds": "20",
        "aspect_ratio": "9:16",
    },
}

client = Client()
events = []

originals = {
    name: getattr(production, name)
    for name in (
        "_generate_final_media_caption",
        "validate_media_post",
        "claim_slot_run",
        "_records",
        "_append",
        "process_one",
        "_clear_clip_failure",
        "_record_clip_failure",
        "_save_media_pdca_records",
        "_record_media_slot_result",
    )
}

try:
    production._generate_final_media_caption = (
        lambda **_kwargs: {
            "status": "PASS",
            "public_post_text": FINAL_TEXT,
            "caption_attempt_count": 1,
            "caption_attempts": [
                {
                    "attempt": 1,
                    "generation_status": "PASS",
                    "semantic_alignment_status": "PASS",
                    "final_validator_status": "PASS",
                    "blocked_reasons": [],
                }
            ],
            "blocked_reasons": [],
            "caption_provider": "test_provider",
            "caption_provider_version": "1",
            "alignment_status": "PASS",
            "final_alignment_score": "0.95",
            "main_claim_coverage": "1.0",
            "unsupported_claim_count": "0",
            "source_copy_similarity": "0.20",
            "recent_post_similarity": "0.10",
            "claim_support_json": "[]",
        }
    )

    production.validate_media_post = (
        lambda payload: {
            "status": (
                "PASS"
                if payload.get("public_post_text")
                == FINAL_TEXT
                else "BLOCKED"
            ),
            "blocked_reasons": (
                []
                if payload.get("public_post_text")
                == FINAL_TEXT
                else ["stale_caption_used"]
            ),
        }
    )

    production.claim_slot_run = (
        lambda *_args, **_kwargs:
        events.append("claim")
        or {"status": "CLAIMED"}
    )

    production._records = (
        lambda *_args, **_kwargs: []
    )

    production._append = (
        lambda *_args, **_kwargs:
        events.append("queue")
    )

    production.process_one = (
        lambda *_args, **_kwargs:
        events.append("publish")
        or {
            "status": "POSTED_SAVE_FAILED",
            "result_id": "result_1",
            "post_url": (
                "https://www.threads.com/"
                "@example/post/1"
            ),
        }
    )

    production._clear_clip_failure = (
        lambda *_args, **_kwargs:
        events.append("clear_failure")
    )

    production._record_clip_failure = (
        lambda *_args, **_kwargs:
        (_ for _ in ()).throw(
            AssertionError(
                "must not retry an externally posted clip"
            )
        )
    )

    production._save_media_pdca_records = (
        lambda *_args, **_kwargs: {
            "saved": 3,
            "skipped": 0,
        }
    )

    production._record_media_slot_result = (
        lambda *_args, **_kwargs: {
            "status": "POSTED_PRIMARY",
        }
    )

    result = production.execute_saved_media_post(
        plan,
        client,
    )

finally:
    for name, value in originals.items():
        setattr(production, name, value)


checks = [
    (
        "posted save failure is terminal",
        result.get("status")
        == "POSTED_SAVE_FAILED",
    ),
    (
        "claim precedes one publish",
        events[:3]
        == ["claim", "queue", "publish"]
        and events.count("publish") == 1,
    ),
    (
        "clip marked posted",
        client.clip_update.get("post_status")
        == "POSTED",
    ),
    (
        "failure state cleared",
        "clear_failure" in events,
    ),
    (
        "final caption used instead of stale text",
        result.get("selected_clip", {}).get(
            "public_post_text"
        )
        == FINAL_TEXT,
    ),
]

for name, ok in checks:
    print(
        f"  {'PASS' if ok else 'FAIL'} {name}"
    )

raise SystemExit(
    0
    if all(ok for _, ok in checks)
    else 1
)
