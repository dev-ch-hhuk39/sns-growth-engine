#!/usr/bin/env python3
"""Static contract for the single-host buffered production runtime."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
launcher = (ROOT / "scripts" / "run_buffered_production_host.sh").read_text()
installer = (ROOT / "scripts" / "install_buffered_production_runtime.sh").read_text()
recovery = (ROOT / ".github" / "workflows" / "content-slot-recovery.yml").read_text()
deploy = (ROOT / ".github" / "workflows" / "deploy-buffered-production-runtime.yml").read_text()
refresh = (ROOT / ".github" / "workflows" / "refresh-threads-tokens.yml").read_text()

assert "flock -n -E 75" in launcher
assert "PRODUCTION_TRIGGER" in launcher
assert "PUBLISH_ENABLED=true ALLOW_REAL_THREADS_POST=true" in launcher
assert "ALLOW_REAL_X_POST=false" in launcher
assert "BEAUTY_PRODUCTION_ENABLED=false" in launcher
assert '"$account" == "beauty_account"' in launcher
assert "BEAUTY_ACTIVATION_APPROVED" in launcher
assert "BEAUTY_PRODUCTION_ENABLED=true" in launcher
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
assert "rsync -a --delete" in installer
assert "--exclude .runtime" in installer
assert "ln -sfn" in installer
assert "runs-on: [self-hosted, Linux, X64]" in recovery
assert "run_buffered_production_host.sh" in recovery
assert "--trigger github_schedule_recovery" in recovery
assert "workflow_dispatch" in deploy
assert "DEPLOY_BUFFERED_RUNTIME" in deploy
assert "runtime.env" in deploy
assert 'splitlines()) != len(keys) + 1' in deploy
assert 'shlex.quote(value)}\\n")' in deploy
assert 'shlex.quote(value)}\\\\n")' not in deploy
assert "run_buffered_production_host.sh" in deploy
assert "COOLDOWN_ACTIVE" in deploy
assert "DAILY_CAP_REACHED" in deploy
assert "no-publish runtime verification found an unsafe delivery failure" in deploy
assert "runs-on: [self-hosted, Linux, X64]" in refresh
assert "/opt/github-runners/sns-growth-engine/.buffered-runtime" in launcher
assert "/opt/github-runners/sns-growth-engine/.buffered-runtime" in installer
assert "THREADS_TOKEN_STORE_DIR: /opt/github-runners/sns-growth-engine/.buffered-runtime/shared/threads_tokens" in refresh
assert "THREADS_APP_ID_BEAUTY_ACCOUNT" in refresh
print("buffered host runtime contract: PASS")
