#!/usr/bin/env python3
"""Physical YouTube routes start and stop the pinned bounded POT provider."""
from __future__ import annotations

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = (
    "direct-media-preparation.yml",
    "approved-source-clip-preparation.yml",
    "media-growth-production-night-scout.yml",
    "media-growth-production.yml",
)

for name in WORKFLOWS:
    path = ROOT / ".github" / "workflows" / name
    text = path.read_text(encoding="utf-8")
    yaml.safe_load(text)
    assert "scripts/start_youtube_pot_provider.sh" in text, name
    assert "scripts/stop_youtube_pot_provider.sh" in text, name
    assert text.index("scripts/start_youtube_pot_provider.sh") < text.index("ALLOW_VIDEO_DOWNLOAD: \"true\""), name
    assert "if: always()" in text, name

start = (ROOT / "scripts/start_youtube_pot_provider.sh").read_text(encoding="utf-8")
assert "@sha256:78502f24ce2b716272cf7d6e146f570069b987e9a77a1b346c161ac5bdb028e6" in start
assert "--publish 127.0.0.1:4416:4416" in start
assert "curl --fail --silent --show-error" in start
assert "seq 1 30" in start

print("PASS test_youtube_pot_provider_workflows.py")
