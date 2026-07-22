#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
wf = (ROOT / ".github/workflows/media-transcription-production.yml").read_text(encoding="utf-8")
checks = [
    ("workflow exists", "name: Media Transcription Production" in wf),
    ("manual diagnostic only", "workflow_dispatch:" in wf and "schedule:" not in wf),
    ("dry-run first", "Dry-run transcription plan" in wf),
    ("local transcription scoped true", 'ALLOW_LOCAL_TRANSCRIPTION: "true"' in wf),
    ("download scoped true", 'ALLOW_VIDEO_DOWNLOAD: "true"' in wf),
    ("no external transcription api", 'ALLOW_TRANSCRIPTION_API: "false"' in wf),
    ("no cut/upload/post", all(token in wf for token in [
        'ALLOW_VIDEO_CUT: "false"',
        'ALLOW_CLOUDINARY_UPLOAD: "false"',
        'ALLOW_MEDIA_POSTS: "false"',
        'ALLOW_REAL_THREADS_VIDEO_POST: "false"',
        'PUBLISH_ENABLED: "false"',
        'ALLOW_REAL_THREADS_POST: "false"',
    ])),
    ("bounded limit", "--limit 1" in wf),
    ("clip generation after transcription", "run_media_growth_engine.py" in wf and "--confirm-media-growth" in wf),
]
failed = [name for name, ok in checks if not ok]
for name, ok in checks:
    print(f"  {'PASS' if ok else 'FAIL'} {name}")
print(f"PASS: {len(checks)-len(failed)} / FAIL: {len(failed)}")
raise SystemExit(1 if failed else 0)
