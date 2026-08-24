#!/usr/bin/env python3
"""The permission seed workflow must stay manual, explicit, and non-operational."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
text = (ROOT / ".github" / "workflows" / "seed-approved-media-permissions.yml").read_text(encoding="utf-8")
checks = {
    "manual only": "workflow_dispatch:" in text and "schedule:" not in text,
    "confirmation required": "confirm_owner_attestation" in text and "--confirm-owner-attestation" in text,
    "canonical registered-owner sources selected": "load_registry" in text and "registered_owner_scope_id" in text,
    "empty canonical scope fails closed": "no canonical registered-owner sources" in text,
    "publishing disabled": 'PUBLISH_ENABLED: "false"' in text and 'ALLOW_REAL_THREADS_POST: "false"' in text,
    "media actions disabled": 'ALLOW_VIDEO_DOWNLOAD: "false"' in text and 'ALLOW_CLOUDINARY_UPLOAD: "false"' in text,
}
for name, ok in checks.items():
    print(f"{'PASS' if ok else 'FAIL'} {name}")
raise SystemExit(0 if all(checks.values()) else 1)
