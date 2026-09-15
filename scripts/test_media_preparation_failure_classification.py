#!/usr/bin/env python3
"""WP3 contracts: provider failures and physical shortages are not conflated."""
from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "src")]

from media.direct_content_understanding import provider_failure_class, vision_summary
from media_activation_source_suitability import account_evidence_hits
import run_media_production_pipeline as pipeline
import requests

response = Mock(status_code=429)
assert provider_failure_class(requests.HTTPError(response=response)) == "rate_limited"
assert provider_failure_class(requests.Timeout()) == "timeout"

before = os.environ.pop("GITHUB_TOKEN", None)
try:
    vision = vision_summary([], media_type="video")
finally:
    if before is not None:
        os.environ["GITHUB_TOKEN"] = before
assert vision["status"] == "UNAVAILABLE"
assert vision["failure_class"] == "auth_missing"

beauty = account_evidence_hits("beauty_account", "洗顔のあとに美容液を少量つける")
night = account_evidence_hits("night_scout", "洗顔のあとに美容液を少量つける")
assert {"洗顔", "美容液"}.issubset(beauty), beauty
assert not night, night

assert pipeline.media_availability_status(0, 1, [{"status": "NO_ELIGIBLE_CLIP"}]) == "RESOURCE_SHORTAGE"
assert pipeline.media_availability_status(0, 1, [{"status": "PREPARATION_FAILED"}]) == "PREPARATION_FAILED"
assert pipeline.media_availability_status(1, 1, []) == "READY"
print("media preparation failure classification: PASS")
