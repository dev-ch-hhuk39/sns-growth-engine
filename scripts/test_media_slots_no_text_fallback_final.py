#!/usr/bin/env python3
from pathlib import Path
import json

root=Path(__file__).resolve().parents[1]
config=json.loads((root/"config/media_growth_engine.json").read_text())
assert config["saved_media_post_fallback"] == "NO_MEDIA_FALLBACK"
for path, cron in (("direct-reference-media-night-scout.yml", '"2 9 * * *"'), ("direct-reference-media-liver-manager.yml", '"4 7 * * *"'), ("media-growth-post-night-scout.yml", '"2 12 * * *"'), ("media-growth-post-liver-manager.yml", '"4 9 * * *"')):
    text=(root/".github/workflows"/path).read_text()
    assert cron in text
    assert "validate_production_activation.py --use-sheets" in text
    assert "FORCE_TEXT_ONLY_FALLBACK" not in text
for path in (root/"scripts/run_direct_reference_media_pipeline.py", root/"scripts/run_media_production_pipeline.py"):
    text=path.read_text(); assert "FORCE_TEXT_ONLY_FALLBACK" not in text; assert "BLOCK_MEDIA_SLOT" in text
print("PASS test_media_slots_no_text_fallback_final.py")
