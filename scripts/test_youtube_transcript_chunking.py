#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = (
    ROOT
    / "scripts"
    / "fetch_youtube_transcripts_for_media_growth.py"
)

spec = importlib.util.spec_from_file_location(
    "bounded_youtube_transcripts",
    MODULE_PATH,
)
module = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(module)

segments = [
    {
        "start": index * 2.0,
        "end": index * 2.0 + 1.8,
        "text": (
            "キャバクラの店舗選びでは"
            "時給だけでなく客層と出勤条件を"
            "確認します。"
            * 8
        ),
    }
    for index in range(260)
]

video = {
    "source_video_id": "sv_long",
    "source_id": "src_long",
    "video_id": "abcdefghijk",
    "canonical_video_url": (
        "https://www.youtube.com/watch"
        "?v=abcdefghijk"
    ),
}

rows = module.build_transcript_rows(
    video=video,
    account_id="night_scout",
    segments=segments,
    language="ja",
)

complete = module.complete_source_video_ids(
    rows
)
incomplete = module.complete_source_video_ids(
    rows[:-1]
)

checks = [
    (
        "long transcript is split",
        len(rows) > 1,
    ),
    (
        "transcript cells stay bounded",
        all(
            len(row["transcript_text"])
            <= module.SHEETS_SAFE_CELL_CHARS
            and len(row["segments_json"])
            <= module.SHEETS_SAFE_CELL_CHARS
            for row in rows
        ),
    ),
    (
        "complete chunk set is recognized",
        "sv_long" in complete,
    ),
    (
        "partial chunk set is not complete",
        "sv_long" not in incomplete,
    ),
    (
        "chunk IDs are deterministic",
        rows[0]["transcript_id"]
        == "tr_sv_long_part_001",
    ),
]

failed = [
    name
    for name, passed in checks
    if not passed
]
for name, passed in checks:
    print(
        f"  {'PASS' if passed else 'FAIL'} "
        f"{name}"
    )
print(
    f"PASS: {len(checks) - len(failed)} "
    f"/ FAIL: {len(failed)}"
)
raise SystemExit(1 if failed else 0)
