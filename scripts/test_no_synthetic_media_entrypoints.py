#!/usr/bin/env python3
"""Synthetic text-card media must never be an executable SNS path."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

FORBIDDEN_PATHS = (
    ".github/workflows/system-owned-media-canaries.yml",
    ".github/workflows/bounded-canary-publish.yml",
    "scripts/run_system_owned_media_canaries.py",
    "scripts/prepare_first_wave_canaries.py",
    "scripts/prepare_remaining_eight_canaries.py",
    "scripts/generate_social_card.py",
    "src/media/social_card.py",
)

FORBIDDEN_MARKERS = (
    "run_system_owned_media_canaries",
    "render_text_card",
    "from media.social_card",
    "GENERATE_SYSTEM_OWNED_MEDIA",
    "PUBLISH_12_APPROVED_CANARIES",
)

errors: list[str] = []

for relative in FORBIDDEN_PATHS:
    if (ROOT / relative).exists():
        errors.append(f"forbidden path exists: {relative}")

self_path = Path(__file__).resolve()

for base in ("scripts", "src", "config", ".github"):
    scan_root = ROOT / base

    if not scan_root.exists():
        continue

    for path in scan_root.rglob("*"):
        if not path.is_file():
            continue
        if path.resolve() == self_path:
            continue
        if "__pycache__" in path.parts:
            continue
        if path.suffix not in {".py", ".json", ".yml", ".yaml"}:
            continue

        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue

        for marker in FORBIDDEN_MARKERS:
            if marker in text:
                errors.append(
                    f"forbidden marker {marker!r}: "
                    f"{path.relative_to(ROOT)}"
                )

if errors:
    raise AssertionError("\n".join(errors))

print("PASS test_no_synthetic_media_entrypoints.py")
