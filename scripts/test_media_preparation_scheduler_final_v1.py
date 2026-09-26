#!/usr/bin/env python3
from pathlib import Path

path = Path(".github/workflows/media-preparation-scheduler.yml")
text = path.read_text(encoding="utf-8")

assert "workflow_dispatch:" in text
assert 'schedule:' not in text
assert 'default: "false"' in text
installer = Path("scripts/install_buffered_production_runtime.sh").read_text(encoding="utf-8")
direct = Path(".github/workflows/direct-media-preparation.yml").read_text(encoding="utf-8")
clip = Path(".github/workflows/approved-source-clip-preparation.yml").read_text(encoding="utf-8")
assert "15 5 * * *" in installer
assert "run_buffered_media_preparation_host.sh" in installer
assert 'cron: "45 1 * * *"' in direct
assert 'schedule:' not in clip
assert "refill-existing-approved-clips:" in direct
assert "direct-media-preparation.yml/dispatches" in text
assert "approved-source-clip-preparation.yml/dispatches" in text
assert "cancel-in-progress: false" in text

# Xserver begins at 05:15 JST and is hard-bounded to 270 minutes (09:45).
# Hosted inventory recovery begins at 10:45 JST, preserving a 60-minute gap.
primary_hour, primary_minute = 5, 15
fallback_hour, fallback_minute = 10, 45
primary_end = primary_hour * 60 + primary_minute + 270
fallback_start = fallback_hour * 60 + fallback_minute
assert fallback_start - primary_end == 60
assert "timeout 270m" in installer
assert "GitHub-hosted preparation" in installer

for workflow in (direct, clip):
    assert workflow.index("Stop bounded YouTube PO Token Provider") < workflow.index("Clean expired transient media")

print("[PASS] Xserver primary and delayed GitHub-hosted fallback are scheduled")
print("[PASS] hosted Direct then uploaded-clip fallback are serialized in one workflow")
print("[PASS] Existing Direct and approved-clip workflows remain connected")
