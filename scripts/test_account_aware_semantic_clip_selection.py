#!/usr/bin/env python3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from video.semantic_clip_planner import plan_semantic_clips


def main() -> int:
    segments = [
        {"start": 0, "end": 12, "text": "どうして最近は毎日忙しいのかを話します。"},
        {"start": 14, "end": 30, "text": "キャバクラで出勤を続けるなら、客層と担当への相談を先に確認します。"},
        {"start": 34, "end": 48, "text": "実は朝の準備を短くするコツもあります。"},
    ]
    rows = plan_semantic_clips(
        segments,
        video_duration=48,
        max_candidates=1,
        preferred_terms=("キャバ", "出勤", "客層", "担当", "相談"),
    )
    ok = len(rows) == 1 and "キャバクラ" in rows[0]["excerpt"]
    print(f"  {'PASS' if ok else 'FAIL'} account terms win over generic hook score")
    print(f"PASS: {1 if ok else 0} / FAIL: {0 if ok else 1}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
