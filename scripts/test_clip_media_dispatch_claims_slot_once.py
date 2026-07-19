#!/usr/bin/env python3
"""Saved clip dispatch claims first and treats POSTED_SAVE_FAILED as terminal."""
import run_media_production_pipeline as production


class Client:
    def __init__(self):
        self.clip_update = {}

    def update_video_clip_candidate(self, _clip_id, **fields):
        self.clip_update = fields

    def save_source_video(self, _row):
        return None


plan = {
    "account_id": "liver_manager",
    "slot_id": "lm_1800_clip_media",
    "selected_clip": {
        "clip_candidate_id": "clip_1",
        "source_video_id": "sv_1",
        "public_post_text": "初見さんが入りやすい配信は、話題を一言共有するところから始まります。",
        "rights_status": "approved_creator_clip",
        "permission_status": "approved",
        "alignment_status": "PASS",
        "final_alignment_score": "0.95",
        "main_claim_coverage": "1.0",
        "unsupported_claim_count": "0",
        "source_copy_similarity": "0.20",
        "recent_post_similarity": "0.10",
    },
    "selected_source_video": {
        "source_video_id": "sv_1",
        "canonical_video_url": "https://www.youtube.com/watch?v=abcdefghijk",
    },
    "selected_media_asset": {
        "media_asset_id": "asset_1",
        "storage_url": "https://res.cloudinary.com/demo/video/upload/clip.mp4",
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
        "validate_media_post", "claim_slot_run", "_records", "_append", "process_one",
        "_clear_clip_failure", "_record_clip_failure", "_save_media_pdca_records",
        "_record_media_slot_result",
    )
}
try:
    production.validate_media_post = lambda _payload: {"status": "PASS", "blocked_reasons": []}
    production.claim_slot_run = lambda *_args, **_kwargs: events.append("claim") or {"status": "CLAIMED"}
    production._records = lambda *_args, **_kwargs: []
    production._append = lambda *_args, **_kwargs: events.append("queue")
    production.process_one = lambda *_args, **_kwargs: events.append("publish") or {
        "status": "POSTED_SAVE_FAILED",
        "result_id": "result_1",
        "post_url": "https://www.threads.com/@example/post/1",
    }
    production._clear_clip_failure = lambda *_args, **_kwargs: events.append("clear_failure")
    production._record_clip_failure = lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("must not retry an externally posted clip"))
    production._save_media_pdca_records = lambda *_args, **_kwargs: {"saved": 3, "skipped": 0}
    production._record_media_slot_result = lambda *_args, **_kwargs: {"status": "POSTED_PRIMARY"}
    result = production.execute_saved_media_post(plan, client)
finally:
    for name, value in originals.items():
        setattr(production, name, value)

checks = [
    ("posted save failure is terminal", result.get("status") == "POSTED_SAVE_FAILED"),
    ("claim precedes one publish", events[:3] == ["claim", "queue", "publish"] and events.count("publish") == 1),
    ("clip marked posted", client.clip_update.get("post_status") == "POSTED"),
    ("failure state cleared", "clear_failure" in events),
]
for name, ok in checks:
    print(f"  {'PASS' if ok else 'FAIL'} {name}")
raise SystemExit(0 if all(ok for _, ok in checks) else 1)
