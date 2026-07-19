#!/usr/bin/env python3
"""Legacy diagnostics must not duplicate scheduled production ownership."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"


def read(name: str) -> str:
    return (WORKFLOWS / name).read_text(encoding="utf-8")


legacy_manual_only = [
    "media-transcription-production.yml",
    "content-daily-dry-run.yml",
    "source-fetch-dry-run.yml",
    "video-reference-dry-run.yml",
]
clip_preparations = [
    read("media-growth-production-night-scout.yml"),
    read("media-growth-production.yml"),
]
clip_dispatchers = [
    read("media-growth-post-night-scout.yml"),
    read("media-growth-post-liver-manager.yml"),
]

checks = [
    (
        "legacy diagnostics are manual only",
        all("workflow_dispatch:" in read(name) and "schedule:" not in read(name) for name in legacy_manual_only),
    ),
    (
        "one scheduled clip preparation per account",
        all("schedule:" in text and "--prepare-only" in text for text in clip_preparations),
    ),
    (
        "clip dispatchers have no Cloudinary write credentials",
        all("CLOUDINARY_API_SECRET" not in text and "--check-cloudinary" not in text for text in clip_dispatchers),
    ),
]

for name, ok in checks:
    print(f"  {'PASS' if ok else 'FAIL'} {name}")
raise SystemExit(0 if all(ok for _, ok in checks) else 1)
