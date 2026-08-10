#!/usr/bin/env python3
"""Video-only reference selection keeps source text bound to its video parent."""
from __future__ import annotations

import importlib.util
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "generate_threads_ideas_from_references.py"


def load_module():
    spec = importlib.util.spec_from_file_location("video_only_generation", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class FakeClient:
    rows = {
        "source_posts": [
            {"source_post_id": "video_parent", "target_account_id": "night_scout", "platform": "threads", "original_post_text": "夜職で長く続けるために、入店前に確認したいことを整理する。", "source_id": "threads_video"},
            {"source_post_id": "image_parent", "target_account_id": "night_scout", "platform": "threads", "original_post_text": "画像だけの投稿は今回の生成対象にしない。", "source_id": "threads_image"},
            {"source_post_id": "youtube_parent", "target_account_id": "night_scout", "platform": "youtube", "original_post_text": "YouTube動画も今回のThreads参照対象にしない。", "source_id": "youtube_video"},
        ],
        "source_post_media": [
            {"source_post_id": "video_parent", "media_type": "video", "media_index": "0"},
            {"source_post_id": "image_parent", "media_type": "image", "media_index": "0"},
            {"source_post_id": "youtube_parent", "media_type": "video", "media_index": "0"},
        ],
        "source_videos": [], "video_transcripts": [], "posted_results": [],
        "strategy_state": [], "metric_snapshots": [], "media_metrics": [],
        "category_scores": [], "learning_rules": [],
    }


def main() -> int:
    module = load_module()
    client = FakeClient()

    def read_records(_client, logical):
        return client.rows.get(logical, [])

    with patch("sheets_record_reader.read_records_safely", side_effect=read_records):
        result = module.run_reference_generation(
            "night_scout", 3, apply=False, video_only_reference=True, client=client,
        )
    checks = [
        ("video filter reported", result["reference_media_filter"] == "video_only"),
        ("only video parent is generation input", result["source_posts"] == 1),
        ("video parent count preserved", result["video_reference_parent_count"] == 1),
        ("review-only candidate status", result["candidate_status"] == "WAITING_REVIEW"),
        ("never worker selectable", result["worker_selectable"] is False),
        ("never posts", result["real_post_possible_now"] is False),
    ]
    failed = [name for name, ok in checks if not ok]
    for name, ok in checks:
        print(f"{'PASS' if ok else 'FAIL'} {name}")
    print(f"PASS: {len(checks) - len(failed)} / FAIL: {len(failed)}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
