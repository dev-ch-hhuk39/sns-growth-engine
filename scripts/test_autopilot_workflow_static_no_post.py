#!/usr/bin/env python3
"""AUTO_READY workflow is scheduled but cannot post."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/autopilot-auto-ready.yml"


def main() -> int:
    src = WORKFLOW.read_text(encoding="utf-8")
    checks = [
        ("schedule present", "schedule:" in src),
        ("dispatch present", "workflow_dispatch:" in src),
        ("skip real post", "--skip-real-post" in src),
        ("no real confirm flag", "--confirm-real-post" not in src),
        ("publish false", 'PUBLISH_ENABLED: "false"' in src),
        ("threads false", 'ALLOW_REAL_THREADS_POST: "false"' in src),
        ("x false", 'ALLOW_REAL_X_POST: "false"' in src),
        ("cloudinary false", 'ALLOW_CLOUDINARY_UPLOAD: "false"' in src),
        ("transcription false", 'ALLOW_TRANSCRIPTION_API: "false"' in src),
        ("no beauty option", "beauty_account" not in src),
    ]
    failed = [name for name, ok in checks if not ok]
    for name, ok in checks:
        print(f"  {'PASS' if ok else 'FAIL'} {name}")
    print(f"PASS: {len(checks)-len(failed)} / FAIL: {len(failed)}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
