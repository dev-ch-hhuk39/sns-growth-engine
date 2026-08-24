#!/usr/bin/env python3
from pathlib import Path

workflow = (
    Path(__file__).resolve().parents[1]
    / ".github/workflows/direct-media-preparation.yml"
).read_text(encoding="utf-8")

assert (
    "strategy:\n"
    "      fail-fast: false\n"
    "      max-parallel: 1\n"
    "      matrix:\n"
    "        account_id:"
) in workflow

assert "target_account:" in workflow
assert "config/managed_accounts.json" in workflow
assert "fromJSON(needs.resolve-accounts.outputs.account_ids)" in workflow
assert "github.event.inputs.target_account" in workflow
assert "route_slot_id" in workflow

assert (
    "ingest_direct_reference_media_reliable.py"
) in workflow

assert (
    "run_direct_reference_media_pipeline_batched.py"
) in workflow

assert 'REQUIRE_PREPARED: "true"' in workflow

assert 'PUBLISH_ENABLED: "false"' in workflow
assert 'ALLOW_REAL_THREADS_POST: "false"' in workflow
assert 'ALLOW_MEDIA_POSTS: "false"' in workflow

print(
    "PASS "
    "test_direct_media_preparation_serialized.py"
)
