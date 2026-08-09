#!/usr/bin/env python3
"""The review-board scheduler may mutate Sheets, never social platforms."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
workflow = (ROOT / ".github" / "workflows" / "publication-review-sync.yml").read_text(encoding="utf-8")
checks = [
    ("scheduled sync exists", "schedule:" in workflow and 'cron: "17 */2 * * *"' in workflow),
    ("uses explicit review sync", "--confirm-review-sync --use-sheets" in workflow),
    ("applies only explicit review decisions", "--confirm-review-decisions --use-sheets" in workflow),
    ("posting remains disabled", 'PUBLISH_ENABLED: "false"' in workflow and 'ALLOW_REAL_THREADS_POST: "false"' in workflow),
    ("media operations remain disabled", 'ALLOW_VIDEO_DOWNLOAD: "false"' in workflow and 'ALLOW_CLOUDINARY_UPLOAD: "false"' in workflow and 'ALLOW_MEDIA_POSTS: "false"' in workflow),
]
failed = [name for name, ok in checks if not ok]
for name, ok in checks:
    print(f"  {'PASS' if ok else 'FAIL'} {name}")
print(f"PASS: {len(checks) - len(failed)} / FAIL: {len(failed)}")
raise SystemExit(1 if failed else 0)
