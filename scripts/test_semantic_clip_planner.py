#!/usr/bin/env python3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from video.semantic_clip_planner import plan_semantic_clips


def segment(start, text, duration=5):
    return {"start": start, "end": start + duration, "text": text}


short = plan_semantic_clips(
    [segment(0, "配信の最初に話題を伝える。", 6), segment(6, "初見がコメントしやすくなる。", 6)],
    video_duration=12,
    max_candidates=3,
)
long_segments = [
    segment(0, "今日は配信について話します。"),
    segment(5, "雑談が続きます。"),
    segment(10, "実は初見が入れない理由があります。"),
    segment(15, "常連だけの会話になると参加しづらい。"),
    segment(20, "まず今の話題を一言伝えてください。"),
    segment(25, "ここから別の話です。"),
    segment(45, "大事なポイントはコメントを拾うことです。"),
    segment(50, "名前を呼ぶと会話の入口になります。"),
    segment(75, "最後に事務所選びの注意を話します。"),
    segment(80, "契約条件を確認してから決めてください。"),
]
long = plan_semantic_clips(long_segments, video_duration=100, max_candidates=3)


def overlap(a, b):
    return max(0, min(a["end"], b["end"]) - max(a["start"], b["start"]))


checks = [
    ("short video produces one clip", len(short) == 1),
    ("long video produces up to three clips", 1 <= len(long) <= 3),
    ("all ranges stay within 8-45 seconds", all(8 <= row["end"] - row["start"] <= 45 for row in long + short)),
    ("semantic windows do not overlap beyond tolerance", all(overlap(left, right) <= 2 for i, left in enumerate(long) for right in long[i + 1:])),
    ("semantic markers drive selection", any("理由" in row["excerpt"] or "ポイント" in row["excerpt"] or "注意" in row["excerpt"] for row in long)),
    ("selection is identified as semantic", all("semantic" in row["selected_reason"] for row in long + short)),
]
for name, ok in checks:
    print(f"  {'PASS' if ok else 'FAIL'} {name}")
failed = [name for name, ok in checks if not ok]
print(f"PASS: {len(checks) - len(failed)} / FAIL: {len(failed)}")
raise SystemExit(1 if failed else 0)
