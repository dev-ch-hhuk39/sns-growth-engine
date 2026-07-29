#!/usr/bin/env python3
from pathlib import Path
import json

root=Path(__file__).resolve().parents[1]
config=json.loads((root/"config/media_growth_engine.json").read_text())
assert config["saved_media_post_fallback"] == "NO_MEDIA_FALLBACK"
for path in ("direct-reference-media-night-scout.yml", "direct-reference-media-liver-manager.yml", "media-growth-post-night-scout.yml", "media-growth-post-liver-manager.yml"):
    text=(root/".github/workflows"/path).read_text()
    assert "schedule:" not in text
    assert "workflow_dispatch:" in text
    assert "Canary gate" in text
    assert "scheduled_publish_activation_gate.py --use-sheets" in text
    assert "FORCE_TEXT_ONLY_FALLBACK" not in text
for path in (root/"scripts/run_direct_reference_media_pipeline.py", root/"scripts/run_media_production_pipeline.py"):
    text=path.read_text(); assert "FORCE_TEXT_ONLY_FALLBACK" not in text; assert "BLOCK_MEDIA_SLOT" in text
print("PASS test_media_slots_no_text_fallback_final.py")
