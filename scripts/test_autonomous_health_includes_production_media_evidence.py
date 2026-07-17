#!/usr/bin/env python3
"""Read-only health output covers every production media evidence tab."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
source = (ROOT / "scripts/check_autonomous_health.py").read_text(encoding="utf-8")
required = [
    "media_permissions",
    "source_posts",
    "source_post_media",
    "source_videos",
    "video_transcripts",
    "video_clip_candidates",
    "media_assets",
    "media_post_results",
    "media_metrics",
    "clip_performance",
    "content_slot_runs",
    "resource_usage",
]
checks = [(f"health reads {name}", f'"{name}"' in source) for name in required]
checks.extend([
    ("health remains dry-run", '"dry_run": True' in source),
    ("health never sets up Sheets", "setup_all" not in source),
    ("source posts scope by target account", 'logical == "source_posts"' in source and 'target_account_id' in source),
    ("parentless media and resource usage remain globally countable", '"source_post_media", "resource_usage"' in source),
])
for name, ok in checks:
    print(f"  {'PASS' if ok else 'FAIL'} {name}")
failed = [name for name, ok in checks if not ok]
print(f"PASS: {len(checks) - len(failed)} / FAIL: {len(failed)}")
raise SystemExit(1 if failed else 0)
