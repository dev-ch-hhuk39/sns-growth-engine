#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from transcription.sheets_limits import MAX_SHEETS_CELL_CHARS, normalize_transcript_row


text = "配信の話。" * 20_000
segments = [
    {"start": index * 1.5, "end": index * 1.5 + 1.4, "text": f"発言{index}。" * 15}
    for index in range(3_000)
]
row = normalize_transcript_row({
    "transcript_id": "tr-large",
    "transcript_text": text,
    "segments_json": json.dumps(segments, ensure_ascii=False),
    "transcript_hash": "full-input-hash",
    "transcription_scope": "FULL",
})
assert len(row["transcript_text"]) < MAX_SHEETS_CELL_CHARS
assert len(row["segments_json"]) < MAX_SHEETS_CELL_CHARS
decoded = json.loads(row["segments_json"])
assert decoded and decoded[0]["start"] == 0
assert decoded[-1]["start"] == segments[-1]["start"]
assert row["transcript_hash"] == "full-input-hash"
assert "SHEETS_BOUNDED" in row["transcription_scope"]
print("PASS test_transcript_sheets_cell_limits.py")
