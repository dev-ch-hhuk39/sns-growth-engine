#!/usr/bin/env python3
"""Test clip execution confirm gates."""
from __future__ import annotations

import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_ROOT, "src"))

from video.video_clip_executor import build_clip_execution_plan


def main() -> int:
    source = {
        "source_id": "src_test_video",
        "candidate_status": "candidate",
        "rights_policy": "unknown",
        "reuse_policy": "reference_only",
        "media_policy": "plan_only",
    }
    clip = {"clip_candidate_id": "clip_001", "account_id": "night_scout", "output_path": "clips/clip_001.mp4"}
    blocked = build_clip_execution_plan(source, clip, cut=True, confirm_cut=False, dry_run=True)
    checks = [
        ("confirmなしcutはBLOCKED", blocked["status"] == "BLOCKED"),
        ("local_path未生成", blocked["local_path"] == ""),
        ("media_asset未登録", blocked["media_asset"] is None),
    ]
    failed = [name for name, ok in checks if not ok]
    for name, ok in checks:
        print(f"  {'PASS' if ok else 'FAIL'} {name}")
    print(f"PASS: {len(checks)-len(failed)} / FAIL: {len(failed)}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
