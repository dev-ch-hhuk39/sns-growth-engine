#!/usr/bin/env python3
from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

SOURCE = Path("scripts/ingest_direct_reference_media_reliable.py")
text = SOURCE.read_text(encoding="utf-8")
tree = ast.parse(text)

node = next(
    item
    for item in tree.body
    if isinstance(item, ast.FunctionDef)
    and item.name == "_materialized_media_available"
)

module = ast.Module(body=[node], type_ignores=[])
ast.fix_missing_locations(module)

namespace: dict[str, Any] = {"Any": Any}
exec(compile(module, str(SOURCE), "exec"), namespace)

available = namespace["_materialized_media_available"]

assert available({
    "cloudinary_status": "UPLOADED",
    "storage_url": "https://res.cloudinary.com/example/video.mp4",
}) is True

assert available({
    "cloudinary_status": "UPLOADED",
    "storage_url": "",
}) is False

assert available({
    "cloudinary_status": "FAILED",
    "storage_url": "https://res.cloudinary.com/example/video.mp4",
}) is False

assert "materialized = _materialized_media_available(media)" in text
assert "and not (materialized and refresh_understanding)" in text

print("[PASS] missing understanding cannot revive an unmaterialized FAILED download")
print("[PASS] materialized media may still refresh content understanding")
