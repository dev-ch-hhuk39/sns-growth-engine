#!/usr/bin/env python3
"""Validate the manual Threads queue worker GitHub Actions workflow."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/threads-queue-worker.yml"


def main() -> int:
    content = WORKFLOW.read_text(encoding="utf-8")
    checks = [
        ("workflow exists", WORKFLOW.exists()),
        ("dispatch only", "workflow_dispatch:" in content and "schedule:" not in content),
        ("account choices", '"night_scout"' in content and '"liver_manager"' in content),
        ("mode choices", '"dry_run"' in content and '"real_post"' in content),
        ("confirm input", "confirm_real_post" in content),
        ("dry-run before process", content.find("Queue worker dry-run") < content.find("Process queue")),
        ("real env scoped", "PUBLISH_ENABLED:" in content and "ALLOW_REAL_THREADS_POST:" in content),
        ("no x publisher", "publish_x_post.py" not in content),
        ("no beauty option", '"beauty_account"' not in content),
        ("verify after", "Sheets verify after processing" in content),
        ("account-specific secrets", "THREADS_ACCESS_TOKEN_NIGHT_SCOUT" in content and "THREADS_ACCESS_TOKEN_LIVER_MANAGER" in content),
        ("sheets secret fallback", "secrets.SNS_MASTER_SHEET_ID" in content and "secrets.SA_JSON_BASE64" in content),
    ]
    failed = [name for name, ok in checks if not ok]
    for name, ok in checks:
        print(f"  {'PASS' if ok else 'FAIL'} {name}")
    print(f"PASS: {len(checks)-len(failed)} / FAIL: {len(failed)}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
