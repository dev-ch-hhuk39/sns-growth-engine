#!/usr/bin/env python3
"""Canonical registry drives production account discovery and extension."""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from accounts.managed_accounts import (  # noqa: E402
    account_choices,
    credential_env_names,
    invalidate_registry_cache,
    managed_account_ids,
    route_slot_id,
)


registry = json.loads((ROOT / "config/managed_accounts.json").read_text(encoding="utf-8"))
assert set(registry["accounts"]) == {
    "night_scout",
    "liver_manager",
    "beauty_account",
    "tiktok_shop",
}
assert managed_account_ids() == tuple(registry["accounts"])
assert account_choices(include_all=True)[0] == "all"

dummy = json.loads(json.dumps(registry))
dummy["accounts"]["future_account"] = {
    "status": "CREDENTIAL_PENDING",
    "production_enabled": False,
    "account_config": "config/accounts/future_account.json",
    "voice_profile_key": "future_account",
    "hybrid_policy_key": "future_account",
    "review_policy": "human_review_all",
    "credential_prefix": "FUTURE_ACCOUNT",
    "scheduled_routes": ["original_text"],
    "route_slots": {
        "direct_reference_media": "future_direct_review",
        "approved_source_clip": "future_clip_review",
    },
    "x_publish_enabled": False,
}
with tempfile.TemporaryDirectory() as temp_dir:
    path = Path(temp_dir) / "managed_accounts.json"
    path.write_text(json.dumps(dummy), encoding="utf-8")
    os.environ["MANAGED_ACCOUNTS_REGISTRY"] = str(path)
    invalidate_registry_cache()
    try:
        assert "future_account" in managed_account_ids()
        assert credential_env_names("future_account")["access_token"] == "THREADS_ACCESS_TOKEN_FUTURE_ACCOUNT"
        assert route_slot_id("future_account", "approved_source_clip") == "future_clip_review"
    finally:
        os.environ.pop("MANAGED_ACCOUNTS_REGISTRY", None)
        invalidate_registry_cache()

runtime_files = (
    "scripts/process_threads_queue.py",
    "scripts/run_autonomous_loop.py",
    "scripts/run_hybrid_ai_queue_gate.py",
    "scripts/collect_threads_metrics.py",
    "scripts/process_threads_metric_jobs.py",
    "scripts/run_growth_attribution_cycle.py",
    "scripts/run_media_production_pipeline.py",
    "scripts/run_direct_reference_media_pipeline.py",
    "scripts/run_hybrid_ready_pipeline.py",
    "scripts/collect_reference_posts.py",
    "scripts/prepare_video_reference.py",
    "scripts/transcribe_video_reference.py",
)
for relative in runtime_files:
    source = (ROOT / relative).read_text(encoding="utf-8")
    assert 'choices=["night_scout"' not in source, relative
    assert '{"night_scout", "liver_manager", "beauty_account"}' not in source, relative

print("PASS: canonical account registry and fifth-account extension contract")
