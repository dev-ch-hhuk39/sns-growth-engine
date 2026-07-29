#!/usr/bin/env python3
from pathlib import Path

text = (Path(__file__).resolve().parents[1] / ".github/workflows/bounded-canary-publish.yml").read_text(encoding="utf-8")
assert "workflow_dispatch:" in text
assert "PUBLISH_12_APPROVED_CANARIES" in text
assert "prepare_bounded_canary_publish.py --apply --confirm-bounded-canary" in text
assert "--queue-id \"$queue_id\" --confirm-real-post" in text
assert 'ALLOW_REAL_X_POST: "false"' in text
assert 'ALLOW_VIDEO_DOWNLOAD: "false"' in text
assert 'ALLOW_CLOUDINARY_UPLOAD: "false"' in text
print("PASS test_bounded_canary_publish_workflow.py")
