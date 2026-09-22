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

clip_workflow = (ROOT / ".github" / "workflows" / "approved-source-clip-preparation.yml").read_text(encoding="utf-8")
assert "runs-on: [self-hosted, Linux, X64]" in clip_workflow
assert "command -v ffmpeg" in clip_workflow
assert "command -v docker" in clip_workflow
assert "apt-get" not in clip_workflow

start = (ROOT / "scripts/start_youtube_pot_provider.sh").read_text(encoding="utf-8")
assert 'PROVIDER_VERSION="2.0.0"' in start
assert "@sha256:ed86b6fdd5e430ddd7c8ce1adb55e1ab54db7c7dbc1bcbf3a82454a85b971164" in start
assert "plugin/server version mismatch" in start
assert "--publish 127.0.0.1:4416:4416" in start
assert "curl --fail --silent --show-error" in start
assert "seq 1 30" in start

print("PASS test_youtube_pot_provider_workflows.py")
