#!/usr/bin/env python3
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def main() -> int:
    cfg = json.loads((ROOT / "config/media_growth_engine.json").read_text())
    workflows = [
        "direct-media-preparation.yml", "direct-reference-media-liver-manager.yml",
        "direct-reference-media-night-scout.yml", "media-growth-production.yml",
        "media-growth-production-night-scout.yml", "media-growth-post-liver-manager.yml",
        "media-growth-post-night-scout.yml",
    ]
    texts = [(ROOT / ".github/workflows" / name).read_text() for name in workflows]
    ok = (
        cfg["source_video_discovery_apply_enabled"] is True
        and cfg["media_public_post_auto_enabled"] is True
        and all("schedule:" not in text and "workflow_dispatch:" in text and "Canary gate" in text for text in texts)
    )
    print(f"  {'PASS' if ok else 'FAIL'} media workflows stay dispatch-only before canaries")
    print(f"PASS: {1 if ok else 0} / FAIL: {0 if ok else 1}")
    return 0 if ok else 1
if __name__ == "__main__":
    raise SystemExit(main())
