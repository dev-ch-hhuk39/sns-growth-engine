#!/usr/bin/env python3
"""Static contract for the single-host buffered production runtime."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
launcher = (ROOT / "scripts" / "run_buffered_production_host.sh").read_text()
installer = (ROOT / "scripts" / "install_buffered_production_runtime.sh").read_text()
recovery = (ROOT / ".github" / "workflows" / "content-slot-recovery.yml").read_text()
deploy = (ROOT / ".github" / "workflows" / "deploy-buffered-production-runtime.yml").read_text()
refresh = (ROOT / ".github" / "workflows" / "refresh-threads-tokens.yml").read_text()
media_preparation = (ROOT / "scripts" / "run_buffered_media_preparation_host.sh").read_text()

assert "flock -n -E 75" in launcher
assert 'flock -w 240 "$sheets_lock_file"' in launcher
assert "PRODUCTION_TRIGGER" in launcher
assert "PUBLISH_ENABLED=true ALLOW_REAL_THREADS_POST=true" in launcher
assert 'posting_enabled="${BUFFERED_POSTING_ENABLED:-false}"' in launcher
assert "[SKIPPED] buffered production posting is disabled" in launcher
assert "ALLOW_MEDIA_POSTS=false ALLOW_REAL_THREADS_VIDEO_POST=false" in launcher
assert "ALLOW_THREADS_CAROUSEL=false ALLOW_THREADS_MIXED_CAROUSEL=false" in launcher
assert "ALLOW_REAL_X_POST=false" in launcher
assert "BEAUTY_PRODUCTION_ENABLED=false" in launcher
assert '"$account" == "beauty_account"' in launcher
assert "BEAUTY_ACTIVATION_APPROVED" in launcher
assert "BEAUTY_PRODUCTION_ENABLED=true" in launcher
assert "P0_ONCE_RUNTIME_GATE_DISABLED" in launcher
assert "P0_ONCE_TEXT_ONLY_ACCOUNT_SCOPE" in launcher
assert "validate_p0_once_runtime.py" in launcher
assert "p0_exact_canary_approval.py" in launcher
assert launcher.index("p0_exact_canary_approval.py") < launcher.index("validate_p0_once_runtime.py")
assert "P0_EXACT_CANARY_OWNER_APPROVAL_MISSING" in launcher
assert "--confirm-reconcile" in launcher
assert "runtime.env" in launcher and "permissions must be 0600" in launcher
assert "reconcile_due_production_slots.py" in launcher
reconciler = (ROOT / "scripts" / "reconcile_due_production_slots.py").read_text()
readiness = (ROOT / "scripts" / "run_production_readiness_acceptance.py").read_text()
assert 'os.environ.get("CODE_REVISION")' in reconciler
assert 'trigger == "xserver_cron"' in readiness
assert 'trigger == "github_schedule_recovery"' in readiness
assert "--confirm-install" in installer
assert "--enable-scheduler" in installer
assert "--confirm-enable" in installer
assert "# BEGIN SNS-GROWTH-BUFFERED" in installer
assert "--account-id night_scout" in installer
assert "--account-id liver_manager" in installer
assert "--account-id beauty_account" in installer
assert "*/5 * * * *" in installer
assert "1-59/5 * * * *" in installer
assert "2-59/5 * * * *" in installer
assert "rsync -a --delete" in installer
assert "--exclude .runtime" in installer
assert "--stage-only" in installer and "--scheduler-only" in installer
assert "implicit activation is disabled" in installer
assert "runs-on: [self-hosted, Linux, X64]" in recovery
assert 'cron: "3-58/5 * * * *"' in recovery
assert "run_buffered_production_host.sh" in recovery
assert "--trigger github_schedule_recovery" in recovery
assert "workflow_dispatch" in deploy
assert "DEPLOY_BUFFERED_RUNTIME" in deploy
assert 'posting_enabled:\n        description: "Allow scheduled Threads publishing after deploy (defaults to no-post)"\n        required: true\n        default: false\n        type: boolean' in deploy
assert "ENABLE_BUFFERED_POSTING" in deploy
assert 'BUFFERED_POSTING_ENABLED: ${{ inputs.posting_enabled }}' in deploy
transaction = (ROOT / "scripts" / "deploy_buffered_runtime_transaction.sh").read_text()
health = (ROOT / "scripts" / "verify_buffered_runtime_health.py").read_text()
writer = (ROOT / "scripts" / "write_buffered_runtime_env.py").read_text()
assert "runtime.env" in transaction
assert "chadult-production-deploy.lock" in transaction
assert "flock -x -w 600" in transaction
assert "--stage-only" in transaction
assert "--scheduler-only --enable-scheduler --confirm-enable" in transaction
assert "rollback health re-verification failed" in transaction
assert "read-only Sheets health" in health
assert "runtime secret" not in writer.lower() or "shlex.quote(value)" in writer
assert "Transactional candidate deploy, health, activation and rollback" in deploy
assert "--enable-scheduler" in deploy
assert "CLOUDINARY_API_SECRET" in deploy and "GEMINI_API_KEY" in deploy
assert "requirements-media-runtime.txt" in installer
assert 'pip" install --quiet --upgrade "pip==26.2.1"' in installer
assert "15 5 * * *" in installer
assert "run_buffered_media_preparation_host.sh" in installer
assert "PUBLISH_ENABLED=false" in media_preparation
assert "ALLOW_REAL_THREADS_POST=false" in media_preparation
assert "ALLOW_REAL_X_POST=false" in media_preparation
assert "run_buffered_media_preparation_host.py" in media_preparation
assert "runs-on: [self-hosted, Linux, X64]" in refresh
assert "/opt/github-runners/sns-growth-engine/.buffered-runtime" in launcher
assert "/opt/github-runners/sns-growth-engine/.buffered-runtime" in installer
assert "THREADS_TOKEN_STORE_DIR: /opt/github-runners/sns-growth-engine/.buffered-runtime/shared/threads_tokens" in refresh
assert "THREADS_APP_ID_BEAUTY_ACCOUNT" in refresh
print("buffered host runtime contract: PASS")
