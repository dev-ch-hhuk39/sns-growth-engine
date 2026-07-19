"""Keep transcript evidence within Google Sheets' 50,000 character cell cap."""
from __future__ import annotations

import json
import math
from typing import Any

MAX_SHEETS_CELL_CHARS = 49_000
TRANSCRIPT_CELL_CHARS = 46_000
SEGMENTS_CELL_CHARS = 46_000


def bounded_cell(value: Any, limit: int = MAX_SHEETS_CELL_CHARS) -> str:
    text = str(value or "")
    if len(text) <= limit:
        return text
    marker = f"\n[TRUNCATED_FOR_SHEETS total_chars={len(text)}]\n"
    available = max(0, limit - len(marker))
    head = available // 2
    return f"{text[:head]}{marker}{text[-(available - head):]}"


def bounded_segments_json(value: Any, limit: int = SEGMENTS_CELL_CHARS) -> tuple[str, bool]:
    if isinstance(value, str):
        try:
            rows = json.loads(value or "[]")
        except json.JSONDecodeError:
            return "[]", bool(value)
    else:
        rows = value or []
    if not isinstance(rows, list):
        return "[]", bool(rows)
    encoded = json.dumps(rows, ensure_ascii=False, separators=(",", ":"))
    if len(encoded) <= limit:
        return encoded, False
    original_count = len(rows)
    stride = max(2, math.ceil(len(encoded) / limit))
    while stride <= max(2, original_count):
        sampled = rows[::stride]
        if rows and (not sampled or sampled[-1] != rows[-1]):
            sampled.append(rows[-1])
        normalized = []
        for item in sampled:
            if isinstance(item, dict):
                copy = dict(item)
                if "text" in copy:
                    copy["text"] = bounded_cell(copy["text"], 2_000)
                normalized.append(copy)
            else:
                normalized.append(bounded_cell(item, 2_000))
        encoded = json.dumps(normalized, ensure_ascii=False, separators=(",", ":"))
        if len(encoded) <= limit:
            return encoded, True
        stride += 1
    return "[]", True


def normalize_transcript_row(row: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(row)
    full_text = str(row.get("transcript_text", "") or "")
    normalized["transcript_text"] = bounded_cell(full_text, TRANSCRIPT_CELL_CHARS)
    segments, segments_bounded = bounded_segments_json(row.get("segments_json", "[]"))
    normalized["segments_json"] = segments
    text_bounded = normalized["transcript_text"] != full_text
    if text_bounded or segments_bounded:
        scope = str(normalized.get("transcription_scope", "") or "FULL")
        if "SHEETS_BOUNDED" not in scope:
            normalized["transcription_scope"] = f"{scope};SHEETS_BOUNDED"
    return normalized
