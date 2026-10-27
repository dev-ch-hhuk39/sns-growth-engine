#!/usr/bin/env bash
# Action-free, no-post AUTO_READY preparation. Source only; installs no jobs.
# Full hosted generation parity is deliberately unavailable: the existing
# generation routes do not all share one proven paid-request budget ledger.
# Explicit reuse or finite owned-original profiles use the existing strict
# READY writer. Neither profile can call paid generation.
set +x
set -euo pipefail
umask 077

account=""
mode=plan
mode_selected=false
confirm_readonly=false
confirm_write=false
reuse_only=false
offline_original_only=false
horizon=24
max_ready=1
max_allocations=2
trigger=manual

usage() {
  echo "usage: $0 --account-id <night_scout|liver_manager|beauty_account> [--plan | --dry-run --confirm-readonly | --apply --confirm-auto-ready (--reuse-only|--offline-original-only)] [--horizon-hours 6|24] [--max-ready 1..3] [--max-bank-allocations 0..6] [--trigger manual|xserver_cron]" >&2
}
while [[ $# -gt 0 ]]; do
  case "$1" in
    --account-id|--horizon-hours|--max-ready|--max-bank-allocations|--trigger)
      [[ $# -ge 2 ]] || { usage; exit 64; }
      case "$1" in
        --account-id) account="$2" ;;
        --horizon-hours) horizon="$2" ;;
        --max-ready) max_ready="$2" ;;
        --max-bank-allocations) max_allocations="$2" ;;
        --trigger) trigger="$2" ;;
      esac
      shift 2 ;;
    --plan|--dry-run|--apply)
      [[ "$mode_selected" == false ]] || { usage; exit 64; }
      mode_selected=true
      mode="${1#--}"; shift ;;
    --confirm-readonly) confirm_readonly=true; shift ;;
    --confirm-auto-ready) confirm_write=true; shift ;;
    --reuse-only) reuse_only=true; shift ;;
    --offline-original-only) offline_original_only=true; shift ;;
    *) usage; exit 64 ;;
  esac
done
case "$account" in night_scout|liver_manager|beauty_account) ;; *) usage; exit 64 ;; esac
case "$trigger" in manual|xserver_cron) ;; *) usage; exit 64 ;; esac
case "$horizon" in 6|24) ;; *) usage; exit 64 ;; esac
[[ "$max_ready" =~ ^[1-3]$ && "$max_allocations" =~ ^[0-6]$ ]] || { usage; exit 64; }
[[ "$trigger" != xserver_cron || "$horizon" == 24 ]] || { usage; exit 64; }
[[ "$reuse_only" != true || "$offline_original_only" != true ]] || { usage; exit 64; }
profile=approved_inventory_reuse
generation_supported=false
if [[ "$offline_original_only" == true ]]; then
  profile=finite_owned_original_catalog
  generation_supported=true
fi
case "$mode" in
  plan)
    [[ "$confirm_readonly" == false && "$confirm_write" == false ]] || { usage; exit 64; }
    printf '{"status":"PLAN_ONLY","account_id":"%s","trigger":"%s","horizon_hours":%s,"profile":"%s","generation_supported":%s,"paid_generation_supported":false,"hosted_workflow_equivalent":false,"stages":["draft_preflight","activation_guard","verify_before","text_inventory","evergreen_bank_24h_only","strict_ready_only","verify_after"],"would_connect":false,"would_write":false,"would_post":false,"github_actions_used":false}\n' "$account" "$trigger" "$horizon" "$profile" "$generation_supported"
    exit 0 ;;
  dry-run)
    [[ "$confirm_readonly" == true && "$confirm_write" == false && "$reuse_only" == false && "$offline_original_only" == false ]] || { usage; exit 64; } ;;
  apply)
    [[ "$confirm_write" == true && "$confirm_readonly" == false ]] || { usage; exit 64; }
    # Never fall through to ordinary maintenance, which can invoke paid AI.
    [[ "$reuse_only" == true || "$offline_original_only" == true ]] || {
      echo '[BLOCKED] full-generation host mode unavailable; choose --reuse-only or --offline-original-only; neither is full hosted parity' >&2
      exit 78
    } ;;
esac

runtime_root="${BUFFERED_RUNTIME_ROOT:-/opt/github-runners/sns-growth-engine/.buffered-runtime}"
[[ "$runtime_root" = /* && "$runtime_root" != *$'\n'* ]] || { echo '[BLOCKED] absolute runtime root required' >&2; exit 78; }
release="$runtime_root/current"
# Caller-selected approval-file paths are deliberately unsupported.
runtime_env="$runtime_root/shared/runtime.env"
locks="$runtime_root/shared/locks"
shared_deploy_lock=/run/lock/chadult-production-deploy.lock
[[ -f "$shared_deploy_lock" && ! -L "$shared_deploy_lock" && -w "$shared_deploy_lock" ]] || {
  echo '[BLOCKED] shared deployment lock unavailable' >&2; exit 78;
}
exec 8<>"$shared_deploy_lock"
flock -s -w 120 8 || { echo '[BLOCKED] deployment in progress' >&2; exit 75; }

# Resolve only after taking the deployment lock and retain this exact path.
[[ -L "$release" && -f "$release/.production-release" && ! -L "$release/.production-release" ]] || {
  echo '[BLOCKED] immutable release marker unavailable' >&2; exit 78;
}
revision="$(cat "$release/.production-release")"
[[ "$revision" =~ ^[0-9a-f]{40}$ ]] || { echo '[BLOCKED] invalid release marker' >&2; exit 78; }
resolved="$(readlink -f "$release")"
[[ "$resolved" == "$runtime_root/releases/$revision" && -d "$resolved" && ! -L "$resolved" ]] || {
  echo '[BLOCKED] immutable release does not match marker' >&2; exit 78;
}
release="$resolved"
python_bin="$release/.venv/bin/python"
# Like the existing health/aftercare entrypoints, accept the trusted release's
# executable venv interpreter, including its approved toolcache symlink.
[[ -x "$python_bin" ]] || { echo '[BLOCKED] immutable Python unavailable' >&2; exit 78; }
for script in auto_ready_draft_preflight.py recover_production_sheets_threads_first.py maintain_text_ready_inventory.py ready_inventory_diagnostics.py ready_evergreen_bank_summary.py run_autopilot_loop.py; do
  [[ -f "$release/scripts/$script" && ! -L "$release/scripts/$script" ]] || {
    echo '[BLOCKED] required immutable preparation entrypoint unavailable' >&2; exit 78;
  }
done
[[ -d "$runtime_root/shared" && ! -L "$runtime_root/shared" && -f "$runtime_env" && ! -L "$runtime_env" ]] || {
  echo '[BLOCKED] protected runtime configuration unavailable' >&2; exit 78;
}
permissions="$(stat -c '%a' "$runtime_env" 2>/dev/null || stat -f '%Lp' "$runtime_env")"
owner_uid="$(stat -c '%u' "$runtime_env" 2>/dev/null || stat -f '%u' "$runtime_env")"
[[ "$permissions" == 600 && ( "$owner_uid" == "$EUID" || "$owner_uid" == 0 ) ]] || {
  echo '[BLOCKED] runtime configuration must be owner-protected 0600' >&2; exit 77;
}

# Process environment cannot supply approvals, Sheets credentials or AI keys.
unset AUTO_READY_WRITE_APPROVED AUTO_READY_ACTIONS_DISABLED_ATTESTED AUTO_READY_OFFLINE_GENERATION_APPROVED BEAUTY_ACTIVATION_APPROVED
unset GCP_SA_JSON_BASE64 SA_JSON_BASE64 GCP_SA_JSON
unset SPREADSHEET_ID SNS_MASTER_SHEET_ID NOTE_MASTER_SHEET_ID GOOGLE_APPLICATION_CREDENTIALS
unset GEMINI_API_KEY GOOGLE_API_KEY OPENAI_API_KEY ANTHROPIC_API_KEY
unset PYTHONPATH PYTHONHOME
set -a
# shellcheck disable=SC1090
source "$runtime_env"
set +a
if [[ "$mode" == apply ]]; then
  [[ "${AUTO_READY_WRITE_APPROVED:-false}" == true && "${AUTO_READY_ACTIONS_DISABLED_ATTESTED:-false}" == true ]] || {
    echo '[BLOCKED] independent AUTO_READY write consent and disabled-Actions attestation required' >&2; exit 77;
  }
  [[ "$account" != beauty_account || "${BEAUTY_ACTIVATION_APPROVED:-false}" == true ]] || {
    echo '[BLOCKED] independent Beauty activation approval required' >&2; exit 77;
  }
  [[ "$offline_original_only" != true || "${AUTO_READY_OFFLINE_GENERATION_APPROVED:-false}" == true ]] || {
    echo '[BLOCKED] independent finite-original generation approval required' >&2; exit 77;
  }
fi
[[ -n "${SA_JSON_BASE64:-}${GCP_SA_JSON_BASE64:-}${GCP_SA_JSON:-}" && -n "${SPREADSHEET_ID:-}${SNS_MASTER_SHEET_ID:-}${NOTE_MASTER_SHEET_ID:-}" ]] || {
  echo '[BLOCKED] protected Sheets configuration missing' >&2; exit 78;
}

# Reuse-only paths never generate. Remove both provider-key aliases, disable
# alternate paid/local providers and prevent mock evidence being promoted.
export GEMINI_API_KEY=""
export GOOGLE_API_KEY=""
export OPENAI_API_KEY=""
export ANTHROPIC_API_KEY=""
export GITHUB_TOKEN=""
export GH_TOKEN=""
export GITHUB_MODELS_TOKEN=""
export GITHUB_MODELS_API_KEY=""
export GITHUB_MODELS_ENABLED=false
export PUBLISH_ENABLED=false ALLOW_REAL_THREADS_POST=false ALLOW_REAL_THREADS_VIDEO_POST=false ALLOW_REAL_X_POST=false
export ALLOW_MEDIA_POSTS=false ALLOW_THREADS_CAROUSEL=false ALLOW_THREADS_MIXED_CAROUSEL=false
export ALLOW_VIDEO_DOWNLOAD=false ALLOW_VIDEO_CUT=false ALLOW_CLOUDINARY_UPLOAD=false
export ALLOW_TRANSCRIPTION_API=false ALLOW_LOCAL_TRANSCRIPTION=false
export MOCK_LLM=false MOCK_SHEETS=false DRY_RUN=false
export DELIVERY_ENGINE=buffered_vps PRODUCTION_TRIGGER="$trigger" CODE_REVISION="$revision" PRODUCTION_RUNTIME_RELEASE="$release"

[[ -d "$locks" && ! -L "$locks" && ! -L "$locks/sheets-io.lock" && ! -L "$locks/$account.lock" ]] || {
  echo '[BLOCKED] shared Sheets/account locks unavailable' >&2; exit 78;
}
exec 9>"$locks/sheets-io.lock"
flock -w 240 9 || { echo '[BLOCKED] shared Sheets lock busy' >&2; exit 75; }
exec 7>"$locks/$account.lock"
flock -n -E 75 7 || { echo '[BLOCKED] account preparation lock busy' >&2; exit 75; }

scratch="$(mktemp -d "$runtime_root/shared/auto-ready.XXXXXX")"
cleanup() { [[ -z "$scratch" ]] || rm -rf -- "$scratch"; }
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
cd "$release"

# Never print raw child stdout/stderr: it may contain unpublished queue IDs,
# content or provider diagnostics. All public receipts below have fixed fields.
run_stage() {
  local stage="$1"
  shift
  local code
  if timeout 35m "$python_bin" -B "$@" > "$scratch/$stage.json" 2> "$scratch/$stage.stderr"; then
    echo "[OK] auto-ready stage=$stage"
    return 0
  else
    code=$?
    echo "[BLOCKED] auto-ready stage=$stage exit=$code; no automatic retry" >&2
    return "$code"
  fi
}

if [[ "$mode" == dry-run ]]; then
  run_stage inventory_preview "$release/scripts/maintain_text_ready_inventory.py" --account-id "$account" --dry-run --use-sheets --horizon-hours "$horizon"
  run_stage inventory_diagnostics "$release/scripts/ready_inventory_diagnostics.py" --account-id "$account" --report "$scratch/inventory_preview.json" --private-stderr "$scratch/inventory_preview.stderr"
  echo '[OK] AUTO_READY_READONLY_COMPLETE writes=false posts=false hosted_workflow_equivalent=false'
  exit 0
fi

run_stage draft_preflight "$release/scripts/auto_ready_draft_preflight.py" --autonomous-text-only --account-id "$account"
run_stage activation_guard - "$account" <<'PY'
import json
import sys
from pathlib import Path
mode = json.loads(Path("config/autonomous_mode.json").read_text())
if (mode.get("kill_switch") is not False
        or mode.get("production_publish_activation_approved") is not True
        or mode.get("auto_ready_enabled") is not True
        or sys.argv[1] not in mode.get("allowed_accounts", [])):
    raise SystemExit(78)
PY
run_stage verify_before "$release/scripts/recover_production_sheets_threads_first.py" --verify-only --text-inventory-scope --account-id "$account" --json
inventory_profile=(--reuse-only)
bank_profile=(--bank-reuse-only)
if [[ "$offline_original_only" == true ]]; then
  inventory_profile=(--offline-original-only)
  bank_profile=(--bank-offline-only)
fi
if run_stage inventory_reuse "$release/scripts/maintain_text_ready_inventory.py" --account-id "$account" --apply --confirm-ready-maintenance --use-sheets --horizon-hours "$horizon" "${inventory_profile[@]}" --max-bank-allocations "$max_allocations"; then
  run_stage inventory_diagnostics "$release/scripts/ready_inventory_diagnostics.py" --account-id "$account" --report "$scratch/inventory_reuse.json" --private-stderr "$scratch/inventory_reuse.stderr"
else
  code=$?
  run_stage inventory_diagnostics "$release/scripts/ready_inventory_diagnostics.py" --account-id "$account" --report "$scratch/inventory_reuse.json" --private-stderr "$scratch/inventory_reuse.stderr" || true
  exit "$code"
fi

# Preserve the hosted workflow's special bank failure behavior: strict READY
# delivery and readback still run, but cannot erase the reserve failure.
bank_failed=false
if [[ "$horizon" == 24 ]]; then
  if ! run_stage evergreen_reuse "$release/scripts/maintain_text_ready_inventory.py" --account-id "$account" --evergreen-bank --apply --confirm-ready-maintenance --use-sheets "${bank_profile[@]}"; then
    bank_failed=true
  fi
  if ! run_stage evergreen_diagnostics "$release/scripts/ready_evergreen_bank_summary.py" --account-id "$account" --report "$scratch/evergreen_reuse.json" --private-stderr "$scratch/evergreen_reuse.stderr"; then
    bank_failed=true
  fi
  if [[ "$bank_failed" == true ]]; then
    run_stage verify_bank_failure "$release/scripts/recover_production_sheets_threads_first.py" --verify-only --text-inventory-scope --account-id "$account" --json
  fi
fi
run_stage strict_ready_only "$release/scripts/run_autopilot_loop.py" --apply --confirm-run --account-id "$account" --auto-ready --ready-only --max-ready "$max_ready" --max-posts 1 --use-sheets --skip-real-post --summary-only
run_stage verify_after "$release/scripts/recover_production_sheets_threads_first.py" --verify-only --text-inventory-scope --account-id "$account" --json
if [[ "$bank_failed" == true ]]; then
  echo '[BLOCKED] AUTO_READY_EVERGREEN_RESERVE_INCOMPLETE posts=false; no automatic retry' >&2
  exit 1
fi
if [[ "$offline_original_only" == true ]]; then
  echo '[OK] AUTO_READY_OFFLINE_ORIGINAL_COMPLETE generation=finite_owned_catalog paid_generation=false posts=false hosted_workflow_equivalent=false'
else
  echo '[OK] AUTO_READY_REUSE_ONLY_COMPLETE generation=false posts=false hosted_workflow_equivalent=false'
fi
