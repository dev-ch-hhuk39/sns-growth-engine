#!/usr/bin/env bash
# Install an immutable VPS release.  This script never copies an arbitrary
# runner worktree into the live path: the caller must name a commit-shaped
# revision and explicitly confirm the installation.
set -euo pipefail

# Keep immutable releases outside the mutable Actions _work checkout, while
# remaining under the self-hosted runner account's writable directory.
RUNTIME_ROOT="${BUFFERED_RUNTIME_ROOT:-/opt/github-runners/sns-growth-engine/.buffered-runtime}"
SOURCE_ROOT=""
REVISION=""
APPLY="false"
CONFIRMED="false"
ENABLE_SCHEDULER="false"
SCHEDULER_CONFIRMED="false"
STAGE_ONLY="false"
SCHEDULER_ONLY="false"

usage() {
  echo "usage: $0 --source-root <checkout> --revision <git-sha> [--dry-run | --apply --confirm-install --stage-only | --apply --confirm-install --scheduler-only --enable-scheduler --confirm-enable]" >&2
}
while [[ $# -gt 0 ]]; do
  case "$1" in
    --source-root) SOURCE_ROOT="${2:-}"; shift 2 ;;
    --revision) REVISION="${2:-}"; shift 2 ;;
    --dry-run) shift ;;
    --apply) APPLY="true"; shift ;;
    --confirm-install) CONFIRMED="true"; shift ;;
    --enable-scheduler) ENABLE_SCHEDULER="true"; shift ;;
    --confirm-enable) SCHEDULER_CONFIRMED="true"; shift ;;
    --stage-only) STAGE_ONLY="true"; shift ;;
    --scheduler-only) SCHEDULER_ONLY="true"; shift ;;
    *) usage; exit 64 ;;
  esac
done

[[ -n "$SOURCE_ROOT" && -f "$SOURCE_ROOT/scripts/reconcile_due_production_slots.py" ]] || { echo "[BLOCKED] source checkout is incomplete" >&2; exit 64; }
[[ "$REVISION" =~ ^[0-9a-f]{7,64}$ ]] || { echo "[BLOCKED] revision must be a commit SHA" >&2; exit 64; }
if [[ "$APPLY" != "true" ]]; then
  echo "[PLAN_ONLY] release=${RUNTIME_ROOT}/releases/${REVISION}"
  exit 0
fi
[[ "$CONFIRMED" == "true" ]] || { echo "[BLOCKED] explicit --confirm-install is required" >&2; exit 64; }
# Direct invocations have the same fail-closed gate as GitHub deployments.
"$(dirname "$0")/check_chadult_vps_deploy_preflight.sh" --min-free-gib 8
if [[ "$STAGE_ONLY" == "$SCHEDULER_ONLY" ]]; then
  echo '[BLOCKED] specify exactly one of --stage-only or --scheduler-only; implicit activation is disabled' >&2
  exit 64
fi
if [[ "$STAGE_ONLY" == "true" && "$ENABLE_SCHEDULER" == "true" ]]; then
  echo '[BLOCKED] scheduler installation is not allowed before health-verified promotion' >&2
  exit 64
fi
if [[ "$SCHEDULER_ONLY" == "true" && "$ENABLE_SCHEDULER" != "true" ]]; then
  echo '[BLOCKED] scheduler-only requires explicitly confirmed scheduler installation' >&2
  exit 64
fi
if [[ "$ENABLE_SCHEDULER" == "true" && "$SCHEDULER_CONFIRMED" != "true" ]]; then
  echo "[BLOCKED] explicit --confirm-enable is required to install cron" >&2
  exit 64
fi

mkdir -p "$RUNTIME_ROOT/releases" "$RUNTIME_ROOT/shared/locks" "$RUNTIME_ROOT/shared/threads_tokens"
target="$RUNTIME_ROOT/releases/$REVISION"
# Standalone stage-only callers must reserve space before making a new
# immutable Python/media environment, even outside the transaction workflow.
if [[ "$STAGE_ONLY" == "true" && ! -d "$target" ]]; then
  "$(dirname "$0")/check_chadult_vps_deploy_preflight.sh" --min-free-gib 9
fi
if [[ "$SCHEDULER_ONLY" == "true" ]]; then
  if [[ ! -f "$target/.production-release" || "$(cat "$target/.production-release")" != "$REVISION" ||
        ! -x "$target/.venv/bin/python" || "$(readlink -f "$RUNTIME_ROOT/current")" != "$target" ]]; then
    echo '[BLOCKED] scheduler-only requires the exact health-verified current release' >&2
    exit 78
  fi
fi
stage=""
cleanup_owned_stage() {
  # Never remove a release, rollback, next candidate or another job's stage.
  if [[ -n "$stage" && -d "$stage" && ! -L "$stage" &&
        "$(dirname "$stage")" == "$RUNTIME_ROOT/releases" &&
        "$(basename "$stage")" == ".stage-${REVISION}."* ]]; then
    rm -rf -- "$stage"
  fi
}
trap cleanup_owned_stage EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
if [[ "$STAGE_ONLY" == "true" && ! -d "$target" ]]; then
  stage="$(mktemp -d "$RUNTIME_ROOT/releases/.stage-${REVISION}.XXXXXX")"
  rsync -a --delete --exclude .git --exclude .runtime --exclude data --exclude output --exclude .ai-tmp "$SOURCE_ROOT/" "$stage/"
  printf '%s\n' "$REVISION" > "$stage/.sns-deploy-stage-owned"
  printf '%s\n' "$REVISION" > "$stage/.production-release"
  # The system Python is 3.10, which Pillow 13 no longer supports. Use the
  # SNS-only, exact-version 3.11.17 toolcache runtime with independently
  # patched COPIES of its Python ELF launchers. It must boot without relying
  # on LD_LIBRARY_PATH or changing shared VPS/system Python settings.
  python3 "$stage/scripts/bootstrap_sns_python311.py" --stage "$stage"
  PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1 nice -n 15 \
    "$stage/.venv/bin/python" -m pip install --quiet --only-binary=:all: --upgrade "pip==26.2.1"
  # Build a NEW immutable runtime with the OSV-verified fixed setuptools.
  # Never mutate the live release or its independent rollback environments.
  PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1 nice -n 15 \
    "$stage/.venv/bin/python" -m pip install --quiet --only-binary=:all: --upgrade "setuptools==84.1.0"
  # Never compile native dependencies or accumulate a second pip wheel cache
  # on this 1.9 GiB multi-service host. Missing binary wheels fail closed.
  PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1 nice -n 15 \
    "$stage/.venv/bin/python" -m pip install --quiet --only-binary=:all: --no-compile -r "$stage/requirements.txt"
  PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1 nice -n 15 \
    "$stage/.venv/bin/python" -m pip install --quiet --only-binary=:all: --no-compile -r "$stage/requirements-media-runtime.txt"
  PIP_NO_CACHE_DIR=1 "$stage/.venv/bin/python" - <<'PY'
import sys
import PIL
from importlib.metadata import version as package_version
assert sys.version_info[:3] == (3, 11, 17), "SNS_RUNTIME_PYTHON_VERSION_MISMATCH"
assert PIL.__version__ == "13.0.0", "SNS_RUNTIME_PILLOW_VERSION_MISMATCH"
assert package_version("setuptools") == "84.1.0", "SNS_RUNTIME_SETUPOOLS_SECURITY_VERSION_MISMATCH"
PY
  "$stage/.venv/bin/python" -m pip check
  # A stage can consume substantial disk; block promotion if the shared
  # 8-GiB safety floor was crossed. EXIT cleans up only this owned stage.
  "$(dirname "$0")/check_chadult_vps_deploy_preflight.sh" --min-free-gib 8
  mv "$stage" "$target"
  stage=""
fi
if [[ "$STAGE_ONLY" == "true" ]]; then
  [[ -f "$target/.production-release" && "$(cat "$target/.production-release")" == "$REVISION" && -x "$target/.venv/bin/python" ]] || {
    echo '[BLOCKED] candidate integrity check failed' >&2; exit 78;
  }
  echo "[OK] immutable candidate staged without activation: $REVISION"
  exit 0
fi
echo "[OK] installing scheduler for already promoted release: $REVISION"

if [[ "$ENABLE_SCHEDULER" == "true" ]]; then
  command -v crontab >/dev/null || { echo "[BLOCKED] crontab is unavailable" >&2; exit 78; }
  command -v logrotate >/dev/null || { echo '[BLOCKED] logrotate is required for bounded SNS logs' >&2; exit 78; }
  mkdir -p "$RUNTIME_ROOT/shared/logs"
  current_crontab="$(mktemp)"
  updated_crontab="$(mktemp)"
  trap 'rm -f "$current_crontab" "$updated_crontab"' EXIT
  crontab -l > "$current_crontab" 2>/dev/null || :
  awk '
    /^# BEGIN SNS-GROWTH-BUFFERED$/ { skip=1; next }
    /^# END SNS-GROWTH-BUFFERED$/ { skip=0; next }
    !skip { print }
  ' "$current_crontab" > "$updated_crontab"
  # Rotate only SNS-owned cron logs; the shared host's log settings are untouched.
  rotation_config="$RUNTIME_ROOT/shared/sns-cron-logrotate.conf"
  cat > "$rotation_config" <<ROTATION
${RUNTIME_ROOT}/shared/logs/*.cron.log {
    size 20M
    rotate 5
    compress
    missingok
    notifempty
    copytruncate
}
ROTATION
  cat >> "$updated_crontab" <<EOF
# BEGIN SNS-GROWTH-BUFFERED
*/5 * * * * /usr/bin/timeout 10m ${RUNTIME_ROOT}/current/scripts/run_buffered_production_host.sh --account-id night_scout --apply --confirm-reconcile --trigger xserver_cron >> ${RUNTIME_ROOT}/shared/logs/night_scout.cron.log 2>&1
1-59/5 * * * * /usr/bin/timeout 10m ${RUNTIME_ROOT}/current/scripts/run_buffered_production_host.sh --account-id liver_manager --apply --confirm-reconcile --trigger xserver_cron >> ${RUNTIME_ROOT}/shared/logs/liver_manager.cron.log 2>&1
2-59/5 * * * * /usr/bin/timeout 10m ${RUNTIME_ROOT}/current/scripts/run_buffered_production_host.sh --account-id beauty_account --apply --confirm-reconcile --trigger xserver_cron >> ${RUNTIME_ROOT}/shared/logs/beauty_account.cron.log 2>&1
# Run after the previous-day Night 25:00 recovery window closes and finish
# before the next 10:00 JST post slot. The scheduled GitHub-hosted preparation
# fallback starts after the full bounded Xserver window plus a 60-minute margin.
15 5 * * * /usr/bin/timeout 270m ${RUNTIME_ROOT}/current/scripts/run_buffered_media_preparation_host.sh >> ${RUNTIME_ROOT}/shared/logs/media-preparation.cron.log 2>&1
10 4 * * * /usr/bin/timeout 2m /usr/bin/flock -n ${RUNTIME_ROOT}/shared/locks/sns-logrotate.lock /usr/sbin/logrotate -s ${RUNTIME_ROOT}/shared/logrotate.status ${RUNTIME_ROOT}/shared/sns-cron-logrotate.conf
# END SNS-GROWTH-BUFFERED
EOF
  crontab "$updated_crontab"
  echo "[OK] buffered primary scheduler installed for three independent accounts"
fi
