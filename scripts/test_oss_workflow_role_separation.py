#!/usr/bin/env python3
"""Production workflows keep research, preparation, posting, and recovery separate."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"


def read(name: str) -> str:
    path = WORKFLOWS / name
    assert path.exists(), name
    return path.read_text(encoding="utf-8")


research = read("source-research.yml")
acquisition = read("account-acquisition.yml")
direct_prep = read("direct-media-preparation.yml")
clip_preps = [read("media-growth-production-night-scout.yml"), read("media-growth-production.yml")]
direct_dispatchers = [read("direct-reference-media-night-scout.yml"), read("direct-reference-media-liver-manager.yml")]
clip_dispatchers = [read("media-growth-post-night-scout.yml"), read("media-growth-post-liver-manager.yml")]
recovery = read("content-slot-recovery.yml")
aftercare = read("production-autopilot-aftercare.yml")
library_health = read("library-health.yml")

checks = [
    ("source research is analysis only", "run_source_research.py" in research and "--confirm-real-post" not in research),
    ("account acquisition does not publish", "acquire_approved_source_posts.py" in acquisition and "--confirm-real-post" not in acquisition),
    ("direct preparation creates READY inventory", "--prepare-only" in direct_prep and "--confirm-real-post" not in direct_prep),
    ("clip preparation is account split", all("--prepare-only" in text for text in clip_preps)),
    ("direct dispatchers use saved inventory only", all("--post-ready" in text and "ingest_direct_reference_media.py" not in text and "acquire_approved_source_posts.py" not in text for text in direct_dispatchers)),
    ("clip dispatchers use saved media only", all("--post-saved-media" in text and "transcribe_approved_source_videos.py" not in text and "ffmpeg" not in text for text in clip_dispatchers)),
    ("recovery does not perform heavy media work", all(term not in recovery for term in ("yt-dlp", "ffmpeg", "transcribe_approved", "ALLOW_VIDEO_DOWNLOAD: \"true\"", "ALLOW_VIDEO_CUT: \"true\"", "ALLOW_CLOUDINARY_UPLOAD: \"true\""))),
    ("aftercare no longer duplicates media preparation", "discover_approved_source_videos.py" not in aftercare and "run_media_growth_engine.py" not in aftercare),
    ("library health is isolated", "schedule:" in library_health and "--confirm-real-post" not in library_health),
]

for name, ok in checks:
    print(f"  {'PASS' if ok else 'FAIL'} {name}")
raise SystemExit(0 if all(ok for _, ok in checks) else 1)
