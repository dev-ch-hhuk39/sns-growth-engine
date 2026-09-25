#!/usr/bin/env python3
from pathlib import Path

path = Path(".github/workflows/media-preparation-scheduler.yml")
text = path.read_text(encoding="utf-8")

assert "workflow_dispatch:" in text
assert 'schedule:' not in text
assert 'default: "false"' in text
installer = Path("scripts/install_buffered_production_runtime.sh").read_text(encoding="utf-8")
assert "15 5 * * *" in installer
assert "run_buffered_media_preparation_host.sh" in installer
assert "direct-media-preparation.yml/dispatches" in text
assert "approved-source-clip-preparation.yml/dispatches" in text
assert "cancel-in-progress: false" in text

print("[PASS] Xserver is the single natural media-preparation scheduler")
print("[PASS] GitHub preparation remains an explicit, confirmed fallback")
print("[PASS] Existing Direct and approved-clip workflows remain connected")
