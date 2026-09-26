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

assert "run_direct_media_preparation_loop.py" in workflow
assert "run_direct_reference_media_pipeline_batched.py" in workflow
assert "direct_media_candidate_attempts" in workflow
assert "--confirm-preparation-loop" in workflow
assert 'cron: "45 1 * * *"' in workflow
assert "--check-only" in workflow
assert "steps.direct_inventory.outputs.shortage == 'true'" in workflow
assert "bash scripts/install_threads_cli.sh" in workflow
assert 'echo "${THREADS_CLI_INSTALL_DIR}" >> "$GITHUB_PATH"' in workflow
assert "python3 -m playwright install --with-deps chromium" in workflow

assert 'PUBLISH_ENABLED: "false"' in workflow
assert 'ALLOW_REAL_THREADS_POST: "false"' in workflow
assert 'ALLOW_MEDIA_POSTS: "false"' in workflow
clip_workflow = (
    Path(__file__).resolve().parents[1]
    / ".github/workflows/approved-source-clip-preparation.yml"
).read_text(encoding="utf-8")
assert "schedule:" not in clip_workflow
assert "if: github.event_name == 'workflow_dispatch'" in clip_workflow
assert "refill-existing-approved-clips:" in workflow
assert "needs: [resolve-accounts, prepare-direct-media]" in workflow
assert "--stored-source-only" in workflow
pipeline = (Path(__file__).resolve().parents[1] / "scripts/run_media_production_pipeline.py").read_text(encoding="utf-8")
assert "select_stored_full_source" in pipeline
assert 'ALLOW_VIDEO_DOWNLOAD: "true"' in workflow
assert 'ALLOW_VIDEO_CUT: "true"' in workflow
assert 'ALLOW_CLOUDINARY_UPLOAD: "true"' in workflow
assert "Check free-tier resource budget" in workflow
assert "Create this run's owned clip workspace" in workflow
assert "Clean this run's owned clip workspace" in workflow
assert "if: github.event_name == 'schedule' || github.event.inputs.confirm_preparation == 'true'" in workflow
assert 'ALLOW_VIDEO_DOWNLOAD: "false"' in workflow
assert 'ALLOW_VIDEO_CUT: "false"' in workflow
assert 'ALLOW_CLOUDINARY_UPLOAD: "false"' in workflow
assert "docker builder prune" not in clip_workflow
assert "pip cache purge" not in clip_workflow

print(
    "PASS "
    "test_direct_media_preparation_serialized.py"
)
