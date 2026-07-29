#!/usr/bin/env python3
from pathlib import Path

text = (Path(__file__).resolve().parents[1] / ".github/workflows/repair-canary-source-integrity.yml").read_text(encoding="utf-8")
assert "workflow_dispatch:" in text
assert "REPAIR_CANARY_SOURCE_IDENTITIES" in text
assert "repair_canary_direct_video_identities.py --apply --confirm-canary-source-repair" in text
assert 'PUBLISH_ENABLED: "false"' in text
assert 'ALLOW_REAL_THREADS_POST: "false"' in text
assert 'ALLOW_VIDEO_DOWNLOAD: "false"' in text
print("PASS test_repair_canary_source_integrity_workflow.py")
