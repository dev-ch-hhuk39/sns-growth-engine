#!/usr/bin/env python3
from pathlib import Path

text = (Path(__file__).resolve().parents[1] / ".github/workflows/final-production-preparation.yml").read_text(encoding="utf-8")
audit_text = (Path(__file__).resolve().parents[1] / "scripts/audit_existing_canary_evidence.py").read_text(encoding="utf-8")
checks = {
    "dispatch only": "workflow_dispatch:" in text and "schedule:" not in text and "pull_request:" not in text,
    "account scope": "options: [all, night_scout, liver_manager]" in text,
    "apply confirmation": "PREPARE_PRODUCTION" in text,
    "orchestrator": "run_final_production_preparation.py" in text,
    "text canaries": "create_missing_text_canaries.py" in text,
    "existing canary audit": "audit_existing_canaries" in text and "audit_existing_canary_evidence.py" in text,
    "audit writes are scoped": "--confirm-existing-evidence" in text and "inputs.audit_existing_canaries == true" in text,
    "artifact": "actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02" in text,
    "unsafe operations disabled": all(f'{key}: "false"' in text for key in ("PUBLISH_ENABLED", "ALLOW_REAL_THREADS_POST", "ALLOW_VIDEO_DOWNLOAD", "ALLOW_VIDEO_CUT", "ALLOW_CLOUDINARY_UPLOAD", "ALLOW_MEDIA_POSTS")),
}
failed = [name for name, ok in checks.items() if not ok]
if "REQUIRED_CANARIES" not in audit_text or "original_text\", \"reference_text\", \"direct_image\", \"direct_carousel\", \"direct_video\", \"generated_clip" not in audit_text:
    failed.append("fixed twelve-canary audit scope")
print("PASS" if not failed else "FAIL: " + ", ".join(failed))
raise SystemExit(bool(failed))
