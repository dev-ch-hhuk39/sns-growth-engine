#!/usr/bin/env python3
"""Contract test for the manual-only production integrity repair workflow."""
from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "production-integrity-reconcile.yml"


def main() -> int:
    text = WORKFLOW.read_text(encoding="utf-8")
    checks = [
        ("manual dispatch only", "workflow_dispatch:" in text and "schedule:" not in text),
        ("production environment", "environment: production" in text),
        ("confirmation required", "confirm_reconcile" in text and "--confirm-reconcile" in text),
        ("reconcile runner", "scripts/reconcile_production_integrity.py" in text),
        ("post gates false", "PUBLISH_ENABLED: \"false\"" in text and "ALLOW_REAL_THREADS_POST: \"false\"" in text),
        ("media gates false", "ALLOW_CLOUDINARY_UPLOAD: \"false\"" in text and "ALLOW_VIDEO_DOWNLOAD: \"false\"" in text),
        ("read-after-write verify", "recover_production_sheets_threads_first.py --verify-only" in text),
    ]
    failed = [name for name, ok in checks if not ok]
    for name, ok in checks:
        print(f"{'PASS' if ok else 'FAIL'} {name}")
    print(f"total={len(checks)} failed={len(failed)}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
