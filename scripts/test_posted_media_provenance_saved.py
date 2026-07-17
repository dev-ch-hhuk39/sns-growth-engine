#!/usr/bin/env python3
"""Posted media rows retain direct/video/clip provenance for dedupe and PDCA."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sheets_client import TAB_DEFINITIONS  # noqa: E402

source = (ROOT / "scripts/process_threads_queue.py").read_text(encoding="utf-8")
required = {"source_post_id", "source_video_id", "clip_candidate_id", "media_asset_id"}
checks = [
    ("posted_results schema has media provenance", required <= set(TAB_DEFINITIONS["posted_results"])),
    ("queue schema has media provenance", required <= set(TAB_DEFINITIONS["queue"])),
    ("save function copies source_post_id", '"source_post_id": queue_row.get("source_post_id", "")' in source),
    ("save function copies source_video_id", '"source_video_id": queue_row.get("source_video_id", "")' in source),
    ("save function copies clip_candidate_id", '"clip_candidate_id": queue_row.get("clip_candidate_id", "")' in source),
]
for name, ok in checks:
    print(f"  {'PASS' if ok else 'FAIL'} {name}")
failed = [name for name, ok in checks if not ok]
print(f"PASS: {len(checks) - len(failed)} / FAIL: {len(failed)}")
raise SystemExit(1 if failed else 0)
