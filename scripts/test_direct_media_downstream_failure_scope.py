#!/usr/bin/env python3
from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

SOURCE = Path("scripts/run_direct_reference_media_pipeline.py")
text = SOURCE.read_text(encoding="utf-8")
tree = ast.parse(text)

node = next(
    item
    for item in tree.body
    if isinstance(item, ast.FunctionDef)
    and item.name == "_materialized_direct_media_quarantine_recoverable"
)

module = ast.Module(body=[node], type_ignores=[])
ast.fix_missing_locations(module)

namespace: dict[str, Any] = {
    "Any": Any,
    "is_quarantined": lambda row: (
        bool(str(row.get("quarantined_at", "")).strip())
        or str(row.get("processing_status", "")).upper() == "QUARANTINED"
    ),
}
exec(compile(module, str(SOURCE), "exec"), namespace)

recoverable = namespace["_materialized_direct_media_quarantine_recoverable"]

media = {
    "processing_status": "QUARANTINED",
    "quarantined_at": "2026-08-26T00:00:00+00:00",
    "media_type": "video",
}
asset = {
    "cloudinary_status": "UPLOADED",
    "storage_url": "https://res.cloudinary.com/example/video/upload/example.mp4",
    "media_type": "video",
}
understanding = {"status": "PASS"}

assert recoverable(media, asset, understanding) is True
assert recoverable(media, asset, {"status": "FAILED"}) is False
assert recoverable(media, {**asset, "storage_url": ""}, understanding) is False
assert recoverable(
    {**media, "processing_status": "READY", "quarantined_at": ""},
    asset,
    understanding,
) is False

idx = text.rfind("        failure_reason = ")
assert idx >= 0

window = text[idx:idx + 1800]

assert "_record_candidate_failure(" not in window
assert "register_failure(" not in window
assert '"failure_scope": "downstream_caption_or_alignment"' in window
assert '"quarantined": False' in window

print("[PASS] downstream caption/alignment failures cannot quarantine source media")
print("[PASS] only already-materialized understood legacy quarantine is recoverable")
