#!/usr/bin/env bash
# Complete immutable deployment within the VPS administrator's global lock.
set -euo pipefail
umask 077
runtime_root="${BUFFERED_RUNTIME_ROOT:-/opt/github-runners/sns-growth-engine/.buffered-runtime}"
source_root=""
revision=""
confirmed=false
schedule=false
while [[ $# -gt 0 ]]; do
  case "$1" in
    --source-root) source_root="${2:-}"; shift 2 ;;
    --revision) revision="${2:-}"; shift 2 ;;
    --confirm-deploy) confirmed=true; shift ;;
    --enable-scheduler) schedule=true; shift ;;
    *) echo '[BLOCKED] unsupported deploy transaction argument' >&2; exit 64 ;;
  esac
done
[[ "$confirmed" == true && "$revision" =~ ^[0-9a-f]{40}$ && -f "$source_root/scripts/reconcile_due_production_slots.py" ]] || {
  echo '[BLOCKED] explicit confirmed revision/source required' >&2; exit 64;
}
[[ -d "$runtime_root/releases" && ! -L "$runtime_root" && ! -L "$runtime_root/releases" &&
   -d "$runtime_root/shared" && ! -L "$runtime_root/shared" ]] || {
  echo '[BLOCKED] SNS immutable runtime or shared root is not installed' >&2; exit 78;
}
common_lock=/run/lock/chadult-production-deploy.lock
[[ -f "$common_lock" && ! -L "$common_lock" && -w "$common_lock" ]] || {
  echo '[BLOCKED] global deployment lock must be provisioned by VPS Ops' >&2; exit 78;
}
exec 9<>"$common_lock"
flock -x -w 600 9 || { echo '[BLOCKED] global deployment lock is busy' >&2; exit 75; }
"$source_root/scripts/check_chadult_vps_deploy_preflight.sh" --min-free-gib 8
current="$runtime_root/current"
[[ -L "$current" ]] || { echo '[BLOCKED] existing current release pointer required' >&2; exit 78; }
old_release="$(readlink -f "$current")"
[[ "$(dirname "$old_release")" == "$runtime_root/releases" &&
   -f "$old_release/.production-release" ]] || {
  echo '[BLOCKED] current release points outside SNS-owned releases' >&2; exit 78;
}
new_release="$runtime_root/releases/$revision"
[[ "$old_release" != "$new_release" ]] || {
  echo '[BLOCKED] revision is already current; deployment requires a new revision' >&2; exit 78;
}
pending="$runtime_root/pending"
if [[ -e "$pending" || -L "$pending" ]]; then
  [[ -L "$pending" && "$(readlink -f "$pending")" == "$new_release" ]] || {
    echo '[BLOCKED] a different pending candidate must be resolved before deployment' >&2; exit 78;
  }
fi
shared="$runtime_root/shared"
live_env="$shared/runtime.env"
[[ -f "$live_env" && ! -L "$live_env" && "$(stat -c '%a' "$live_env")" == 600 ]] || {
  echo '[BLOCKED] active production environment is absent or not 0600' >&2; exit 78;
}
staged_env="$shared/.next-runtime-env.${revision}.$$"
posting_env="$shared/.next-runtime-env.${revision}.$$.enabled"
requested_posting="${BUFFERED_POSTING_ENABLED:-false}"
case "$requested_posting" in true|false) ;; *) echo '[BLOCKED] invalid posting mode' >&2; exit 64 ;; esac
backup_env="$shared/.old-runtime-env.${revision}.$$"
backup_cron="$shared/.old-cron.${revision}.$$"
old_previous=""
if [[ -L "$runtime_root/previous" ]]; then old_previous="$(readlink "$runtime_root/previous")"; fi
promoted=false
completed=false
atomic_pointer() {
  local destination="$1"; local release="$2"; local stage="$destination.$$.new"
  ln -s "$release" "$stage"
  mv -Tf "$stage" "$destination"
}
finish() {
  local code="$?"
  trap - EXIT INT TERM
  if [[ "$completed" != true && "$promoted" == true ]]; then
    echo '[WARN] deployment failed after activation; restoring previous runtime' >&2
    if ! atomic_pointer "$current" "$old_release"; then
      echo '[CRITICAL] current rollback pointer could not be restored' >&2
      code=90
    fi
    if [[ -f "$backup_env" ]]; then
      if ! cp -p "$backup_env" "$live_env"; then
        echo '[CRITICAL] previous runtime environment could not be restored' >&2
        code=90
      fi
    fi
    if [[ -f "$backup_cron" ]]; then
      crontab "$backup_cron" || { echo '[CRITICAL] previous cron restoration failed' >&2; code=90; }
    fi
    if [[ -n "$old_previous" ]]; then
      atomic_pointer "$runtime_root/previous" "$old_previous" || { echo '[CRITICAL] previous pointer restore failed' >&2; code=90; }
    fi
    if ! "$source_root/scripts/verify_buffered_runtime_health.py" --release "$old_release" \
         --revision "$(cat "$old_release/.production-release")" --env-file "$live_env"; then
      echo '[CRITICAL] rollback health re-verification failed' >&2
      code=90
    fi
  fi
  rm -f -- "$staged_env" "$backup_env" "$backup_cron" "$shared/.deploy-live-env.$$"     "$current.$$.new" "$pending.$$.new" "$runtime_root/previous.$$.new"
  flock -u 9 || true
  exit "$code"
}
trap finish EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
BUFFERED_POSTING_ENABLED=false python3 "$source_root/scripts/write_buffered_runtime_env.py" \
  --runtime-root "$runtime_root" --out "$staged_env" \
  --inherit-local-p0 "$live_env"
cp -p "$live_env" "$backup_env"
(crontab -l 2>/dev/null || true) > "$backup_cron"
"$source_root/scripts/install_buffered_production_runtime.sh" \
  --source-root "$source_root" --revision "$revision" --apply --confirm-install --stage-only
if [[ ! -L "$pending" ]]; then atomic_pointer "$pending" "$new_release"; fi
THREADS_CLI_INSTALL_DIR="$shared/threads-cli" bash "$source_root/scripts/install_threads_cli.sh"
[[ -x "$(command -v ffmpeg)" && -x "$(command -v xvfb-run)" ]] || {
  echo '[BLOCKED] media runtime binaries unavailable' >&2; exit 78;
}
# Read-only Sheets readiness, imports, exact SHA and non-publishing gates before switching.
"$source_root/scripts/verify_buffered_runtime_health.py" --release "$new_release" \
  --revision "$revision" --env-file "$staged_env"
# Point in time handover: new config and current pointer are protected by EXIT rollback.
promoted=true
# Apply the new environment with posting OFF first. If SIGKILL occurs before
# post-switch health succeeds, old or new code cannot start publishing.
cp -p "$staged_env" "$shared/.deploy-live-env.$$"
mv -Tf "$shared/.deploy-live-env.$$" "$live_env"
atomic_pointer "$current" "$new_release"
"$source_root/scripts/verify_buffered_runtime_health.py" --release "$new_release" \
  --revision "$revision" --env-file "$live_env"
if [[ "$schedule" == true ]]; then
  "$source_root/scripts/install_buffered_production_runtime.sh" \
    --source-root "$source_root" --revision "$revision" --apply --confirm-install \
    --scheduler-only --enable-scheduler --confirm-enable
fi
atomic_pointer "$runtime_root/previous" "$old_release"
if [[ "$requested_posting" == true ]]; then
  BUFFERED_POSTING_ENABLED=true python3 "$source_root/scripts/write_buffered_runtime_env.py" \
    --runtime-root "$runtime_root" --out "$posting_env" \
    --inherit-local-p0 "$backup_env"
  mv -Tf "$posting_env" "$live_env"
fi
if [[ -L "$pending" && "$(readlink -f "$pending")" == "$new_release" ]]; then
  rm -- "$pending"
fi
completed=true
# Retain explicit previous/current/pending releases. Only marked, >=7-day-old,
# SNS-owned interrupted installation stages may be removed, max two per deploy.
python3 "$source_root/scripts/cleanup_owned_sns_deploy_stages.py" \
  --runtime-root "$runtime_root" --apply --confirm-owned-stage-cleanup || \
  echo '[WARN] stale-stage cleanup skipped; live release remains protected' >&2
echo "[OK] immutable runtime promoted with rollback and Sheets verification: $revision"
