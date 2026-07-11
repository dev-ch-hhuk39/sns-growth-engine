#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
wf = (ROOT / ".github/workflows/production-autopilot-aftercare.yml").read_text(encoding="utf-8")

checks = [
    ("workflow has schedule", "schedule:" in wf and 'cron: "40 14 * * *"' in wf),
    ("workflow dispatch exists", "workflow_dispatch:" in wf and "confirm_aftercare" in wf),
    ("publish disabled globally", 'PUBLISH_ENABLED: "false"' in wf),
    ("threads real post disabled", 'ALLOW_REAL_THREADS_POST: "false"' in wf),
    ("x disabled", 'ALLOW_REAL_X_POST: "false"' in wf),
    ("media post disabled", 'ALLOW_MEDIA_POSTS: "false"' in wf and 'ALLOW_REAL_THREADS_VIDEO_POST: "false"' in wf),
    ("download cut upload disabled", 'ALLOW_VIDEO_DOWNLOAD: "false"' in wf and 'ALLOW_VIDEO_CUT: "false"' in wf and 'ALLOW_CLOUDINARY_UPLOAD: "false"' in wf),
    ("transcription disabled", 'ALLOW_TRANSCRIPTION_API: "false"' in wf),
    ("metrics apply step", "collect_threads_metrics.py" in wf and "--confirm-metrics" in wf and "--use-sheets" in wf),
    ("pdca apply step", "generate_next_queue_from_metrics.py" in wf and "--confirm-generate" in wf),
    ("media discovery apply step", "discover_approved_source_videos.py" in wf and "--confirm-discovery" in wf),
    ("real bounded discovery enabled", "--fetch-real" in wf),
    ("source registry sync step", "seed_source_registry.py" in wf and "--confirm-seed" in wf),
    ("source registry sync skips quota-heavy setup", "--skip-setup" in wf),
    ("media growth apply step", "run_media_growth_engine.py" in wf and "--confirm-media-growth" in wf),
    ("no real post command", "--confirm-real-post" not in wf),
    ("no upload/download/cut confirm", "--confirm-upload" not in wf and "--confirm-download" not in wf and "--confirm-cut" not in wf),
]

failed = [name for name, ok in checks if not ok]
for name, ok in checks:
    print(f"  {'PASS' if ok else 'FAIL'} {name}")
print(f"PASS: {len(checks)-len(failed)} / FAIL: {len(failed)}")
raise SystemExit(1 if failed else 0)
