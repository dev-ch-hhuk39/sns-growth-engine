#!/usr/bin/env python3
"""Direct preparation must isolate Sheets-heavy phases without weakening gates."""

from pathlib import Path


workflow = Path(".github/workflows/direct-media-preparation.yml").read_text(
    encoding="utf-8"
)

assert "Cool down shared Sheets quota before acquisition" in workflow
assert "Cool down shared Sheets quota before preparation" in workflow
assert workflow.count("sleep 70") == 2
assert "id: acquisition" in workflow
assert "continue-on-error: true" in workflow
assert "acquisition_outcome=${{ steps.acquisition.outcome }}" in workflow

# Acquisition may fail soft, but every permission, budget and publisher guard
# remains mandatory in the subsequent preparation path.
for required in (
    "Check free-tier preparation budget",
    "Guard direct preparation",
    "ALLOW_VIDEO_DOWNLOAD: \"true\"",
    "ALLOW_CLOUDINARY_UPLOAD: \"true\"",
    "Promote strict autonomous Direct Media to READY",
    "PUBLISH_ENABLED: \"false\"",
    "ALLOW_REAL_THREADS_POST: \"false\"",
    "ALLOW_REAL_X_POST: \"false\"",
):
    assert required in workflow, required

print("[PASS] direct media preparation spaces Sheets-heavy phases and preserves hard gates")
