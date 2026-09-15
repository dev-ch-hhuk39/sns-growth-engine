#!/usr/bin/env bash
# The only host-side entrypoint allowed to publish buffered production slots.
# GitHub recovery and the VPS cron both invoke this file.  It deliberately
# resolves the immutable current release instead of a runner checkout.
set -euo pipefail

# This is deliberately outside the Actions _work checkout but within the
# self-hosted runner's owned directory. The runner account cannot write /opt
# directly on the production host.
RUNTIME_ROOT="${BUFFERED_RUNTIME_ROOT:-/opt/github-runners/sns-growth-engine/.buffered-runtime}"
CURRENT_RELEASE="${RUNTIME_ROOT}/current"
RUNTIME_ENV_FILE="${BUFFERED_RUNTIME_ENV_FILE:-${RUNTIME_ROOT}/shared/runtime.env}"
LOCK_DIR="${RUNTIME_ROOT}/shared/locks"
ACCOUNT_ID=""
MODE="dry-run"
CONFIRMED="false"
TRIGGER="manual"

usage() {
  echo "usage: $0 --account-id <all|night_scout|liver_manager|beauty_account> [--dry-run | --apply --confirm-reconcile] [--trigger <xserver_cron|github_schedule_recovery|manual>]" >&2
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --account-id) ACCOUNT_ID="${2:-}"; shift 2 ;;
    --dry-run) MODE="dry-run"; shift ;;
    --apply) MODE="apply"; shift ;;
    --confirm-reconcile) CONFIRMED="true"; shift ;;
    --trigger) TRIGGER="${2:-}"; shift 2 ;;
    *) usage; exit 64 ;;
  esac
done

case "$ACCOUNT_ID" in all|night_scout|liver_manager|beauty_account) ;; *) usage; exit 64 ;; esac
case "$TRIGGER" in xserver_cron|github_schedule_recovery|manual) ;; *) usage; exit 64 ;; esac
if [[ "$MODE" == "apply" && "$CONFIRMED" != "true" ]]; then
  echo "[BLOCKED] explicit --confirm-reconcile is required" >&2
  exit 64
fi
if [[ ! -x "$CURRENT_RELEASE/scripts/reconcile_due_production_slots.py" && ! -f "$CURRENT_RELEASE/scripts/reconcile_due_production_slots.py" ]]; then
  echo "[BLOCKED] immutable production release is not installed" >&2
  exit 78
fi
if [[ ! -f "$RUNTIME_ENV_FILE" ]]; then
  echo "[BLOCKED] production runtime environment is not installed" >&2
  exit 78
fi

# Do not print or inspect values from the environment file.  Mode 0600 is a
# fail-closed contract: a world-readable secret file must never be sourced.
mode="$(stat -c '%a' "$RUNTIME_ENV_FILE" 2>/dev/null || stat -f '%Lp' "$RUNTIME_ENV_FILE")"
if [[ "$mode" != "600" ]]; then
  echo "[BLOCKED] production runtime environment permissions must be 0600" >&2
  exit 77
fi
set -a
# shellcheck disable=SC1090
source "$RUNTIME_ENV_FILE"
set +a

mkdir -p "$LOCK_DIR"
export DELIVERY_ENGINE="buffered_vps"
export CODE_REVISION="$(cat "$CURRENT_RELEASE/.production-release" 2>/dev/null || true)"
export PRODUCTION_TRIGGER="$TRIGGER"
export PRODUCTION_RUNTIME_RELEASE="$CURRENT_RELEASE"
export THREADS_TOKEN_STORE_DIR="${THREADS_TOKEN_STORE_DIR:-${RUNTIME_ROOT}/shared/threads_tokens}"

run_account() {
  local account="$1"
  local lock_file="${LOCK_DIR}/${account}.lock"
  local invocation_id
  invocation_id="${TRIGGER}_$(date -u +%Y%m%dT%H%M%SZ)_$$"
  export PRODUCTION_HOST_EXECUTION_ID="$invocation_id"
  set +e
  flock -n -E 75 "$lock_file" bash -c '
      set -euo pipefail
      root="$1"; mode="$2"; account="$3"
      python_bin="$root/.venv/bin/python"
      if [[ ! -x "$python_bin" ]]; then python_bin="python3"; fi
      if [[ "$mode" == "apply" ]]; then
        export PUBLISH_ENABLED=true ALLOW_REAL_THREADS_POST=true
        export ALLOW_REAL_X_POST=false
        exec "$python_bin" "$root/scripts/reconcile_due_production_slots.py" --account-id "$account" --apply --confirm-reconcile
      fi
      exec "$python_bin" "$root/scripts/reconcile_due_production_slots.py" --account-id "$account" --dry-run
    ' _ "$CURRENT_RELEASE" "$MODE" "$account"
  local code=$?
  set -e
  if [[ "$code" != "0" ]]; then
    if [[ "$code" == "75" ]]; then
      echo "[SKIPPED] ${account}: another host execution holds the lock"
      return 0
    fi
    return "$code"
  fi
}

if [[ "$ACCOUNT_ID" == "all" ]]; then
  for account in night_scout liver_manager beauty_account; do run_account "$account"; done
else
  run_account "$ACCOUNT_ID"
fi
