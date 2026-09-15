#!/usr/bin/env bash
# Install an immutable VPS release.  This script never copies an arbitrary
# runner worktree into the live path: the caller must name a commit-shaped
# revision and explicitly confirm the installation.
set -euo pipefail

RUNTIME_ROOT="${BUFFERED_RUNTIME_ROOT:-/opt/sns-growth-engine}"
SOURCE_ROOT=""
REVISION=""
APPLY="false"
CONFIRMED="false"
ENABLE_SCHEDULER="false"
SCHEDULER_CONFIRMED="false"

usage() {
  echo "usage: $0 --source-root <checkout> --revision <git-sha> [--dry-run | --apply --confirm-install [--enable-scheduler --confirm-enable]]" >&2
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
if [[ "$ENABLE_SCHEDULER" == "true" && "$SCHEDULER_CONFIRMED" != "true" ]]; then
  echo "[BLOCKED] explicit --confirm-enable is required to install cron" >&2
  exit 64
fi

mkdir -p "$RUNTIME_ROOT/releases" "$RUNTIME_ROOT/shared/locks" "$RUNTIME_ROOT/shared/threads_tokens"
target="$RUNTIME_ROOT/releases/$REVISION"
if [[ ! -d "$target" ]]; then
  stage="$(mktemp -d "$RUNTIME_ROOT/releases/.stage-${REVISION}.XXXXXX")"
  rsync -a --delete --exclude .git --exclude .runtime --exclude data --exclude output --exclude .ai-tmp "$SOURCE_ROOT/" "$stage/"
  printf '%s\n' "$REVISION" > "$stage/.production-release"
  python3 -m venv "$stage/.venv"
  "$stage/.venv/bin/pip" install --quiet -r "$stage/requirements.txt"
  mv "$stage" "$target"
fi
ln -sfn "$target" "$RUNTIME_ROOT/current"
echo "[OK] production runtime release installed: $REVISION"

if [[ "$ENABLE_SCHEDULER" == "true" ]]; then
  command -v crontab >/dev/null || { echo "[BLOCKED] crontab is unavailable" >&2; exit 78; }
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
  cat >> "$updated_crontab" <<EOF
# BEGIN SNS-GROWTH-BUFFERED
*/5 * * * * /usr/bin/timeout 10m ${RUNTIME_ROOT}/current/scripts/run_buffered_production_host.sh --account-id night_scout --apply --confirm-reconcile --trigger xserver_cron >> ${RUNTIME_ROOT}/shared/logs/night_scout.cron.log 2>&1
*/5 * * * * /usr/bin/timeout 10m ${RUNTIME_ROOT}/current/scripts/run_buffered_production_host.sh --account-id liver_manager --apply --confirm-reconcile --trigger xserver_cron >> ${RUNTIME_ROOT}/shared/logs/liver_manager.cron.log 2>&1
*/5 * * * * /usr/bin/timeout 10m ${RUNTIME_ROOT}/current/scripts/run_buffered_production_host.sh --account-id beauty_account --apply --confirm-reconcile --trigger xserver_cron >> ${RUNTIME_ROOT}/shared/logs/beauty_account.cron.log 2>&1
# END SNS-GROWTH-BUFFERED
EOF
  crontab "$updated_crontab"
  echo "[OK] buffered primary scheduler installed for three independent accounts"
fi
