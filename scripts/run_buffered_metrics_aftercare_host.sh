#!/usr/bin/env bash
# Action-free 24h / 72h / 168h Threads metrics-aftercare entrypoint.
#
# Source only: do not install cron or invoke real providers in development.
# Operator/VPS Ops owns protected configuration and the production schedule.
# `--plan` is fully offline and never reads runtime credentials.
set +x
set -euo pipefail
umask 077

account=""
mode="plan"
confirmed_readonly="false"
confirmed_metrics="false"
feedback_preview="false"
health_check="false"
strategy_apply="false"
ready_bank_reuse="false"
bank_allocations=2
trigger="manual"

usage() {
  echo "usage: $0 --account-id <night_scout|liver_manager|beauty_account> [--plan | --dry-run --confirm-readonly | --apply --confirm-metrics] [--with-feedback-preview] [--with-health-check] [--with-strategy-apply] [--with-ready-bank-reuse] [--max-bank-allocations 0..6] [--trigger manual|xserver_cron]" >&2
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --account-id)
      [[ $# -ge 2 ]] || { usage; exit 64; }
      account="$2"; shift 2 ;;
    --plan)
      [[ "$mode" == "plan" ]] || { usage; exit 64; }
      mode="plan"; shift ;;
    --dry-run)
      [[ "$mode" == "plan" ]] || { usage; exit 64; }
      mode="dry-run"; shift ;;
    --apply)
      [[ "$mode" == "plan" ]] || { usage; exit 64; }
      mode="apply"; shift ;;
    --confirm-readonly) confirmed_readonly=true; shift ;;
    --confirm-metrics) confirmed_metrics=true; shift ;;
    --with-feedback-preview) feedback_preview=true; shift ;;
    --with-health-check) health_check=true; shift ;;
    --with-strategy-apply) strategy_apply=true; shift ;;
    --with-ready-bank-reuse) ready_bank_reuse=true; shift ;;
    --max-bank-allocations)
      [[ $# -ge 2 ]] || { usage; exit 64; }
      bank_allocations="$2"; shift 2 ;;
    --trigger)
      [[ $# -ge 2 ]] || { usage; exit 64; }
      trigger="$2"; shift 2 ;;
    *) usage; exit 64 ;;
  esac
done

# Each managed account remains isolated. Beauty requires independent protected
# activation and metrics consent before any confirmed live invocation.
case "$account" in
  night_scout|liver_manager|beauty_account) ;;
  *) usage; exit 64 ;;
esac
case "$trigger" in
  manual|xserver_cron) ;;
  *) usage; exit 64 ;;
esac
if [[ "$health_check" == true && "$account" != night_scout && "$account" != liver_manager ]]; then
  echo "[BLOCKED] strict runtime health is limited to Night and Liver" >&2
  exit 64
fi
[[ "$bank_allocations" =~ ^[0-6]$ ]] || {
  echo "[BLOCKED] bank reuse limit must be 0..6" >&2
  exit 64
}
# Persisting strategy or allocating existing READY candidates is
# owner-authorized, one-account manual canary work. Cron cannot silently
# start these two write paths even if a stale private env flag remains set.
if [[ "$strategy_apply" == true || "$ready_bank_reuse" == true ]]; then
  [[ "$mode" == "apply" && "$trigger" == "manual" &&
     "$confirmed_metrics" == true ]] || {
    echo "[BLOCKED] feedback writes require explicit manual apply mode" >&2
    exit 64
  }
fi
if [[ "$mode" == "plan" ]]; then
  [[ "$confirmed_readonly" == false && "$confirmed_metrics" == false ]] || {
    echo "[BLOCKED] confirmations require an explicit execution mode" >&2
    exit 64
  }
  printf '{"status":"PLAN_ONLY","account_id":"%s","trigger":"%s","stage":"metrics_24_72_168","feedback_preview":%s,"health_check":%s,"feedback_stages":["measured_attribution","next_text_ready_coverage"],"would_connect":false,"would_write":false,"would_post":false,"github_actions_used":false}\n' "$account" "$trigger" "$feedback_preview" "$health_check"
  exit 0
fi

if [[ "$mode" == "dry-run" && "$confirmed_readonly" != true ]]; then
  echo "[BLOCKED] --dry-run requires --confirm-readonly" >&2
  exit 64
fi
if [[ "$mode" == "apply" && "$confirmed_metrics" != true ]]; then
  echo "[BLOCKED] --apply requires --confirm-metrics" >&2
  exit 64
fi
if [[ "$mode" == "dry-run" && "$confirmed_metrics" == true ]] ||
   [[ "$mode" == "apply" && "$confirmed_readonly" == true ]]; then
  echo "[BLOCKED] mutually exclusive readonly/write confirmations" >&2
  exit 64
fi

runtime_root="${BUFFERED_RUNTIME_ROOT:-/opt/github-runners/sns-growth-engine/.buffered-runtime}"
[[ "$runtime_root" = /* ]] || {
  echo "[BLOCKED] runtime root must be absolute" >&2
  exit 78
}
release="$runtime_root/current"
runtime_env="$runtime_root/shared/runtime.env"
locks="$runtime_root/shared/locks"
shared_deploy_lock="/run/lock/chadult-production-deploy.lock"

# Acquire the global deployment lock BEFORE resolving the mutable current
# symlink. Promotion can change it atomically; never inspect one release and
# run a different one. The same global lock protects the whole invocation.
[[ -f "$shared_deploy_lock" && ! -L "$shared_deploy_lock" &&
   -w "$shared_deploy_lock" ]] || {
  echo "[BLOCKED] shared VPS deployment lock is unavailable" >&2
  exit 78
}
exec 8<>"$shared_deploy_lock"
flock -s -w 120 8 || {
  echo "[BLOCKED] deployment currently holds the shared lock" >&2
  exit 75
}

# Deployment contract uses current -> releases/<exact SHA> symlink.
[[ -L "$release" && -f "$release/.production-release" &&
   ! -L "$release/.production-release" &&
   -f "$release/scripts/process_threads_metric_jobs.py" &&
   -x "$release/.venv/bin/python" ]] || {
  echo "[BLOCKED] immutable aftercare release is not installed" >&2
  exit 78
}
revision="$(cat "$release/.production-release")"
[[ "$revision" =~ ^[0-9a-f]{40}$ ]] || {
  echo "[BLOCKED] invalid immutable release marker" >&2
  exit 78
}
resolved="$(readlink -f "$release")"
[[ "$resolved" == "$runtime_root/releases/$revision" &&
   -d "$resolved" && ! -L "$resolved" ]] || {
  echo "[BLOCKED] current release does not match the verified marker" >&2
  exit 78
}
release="$resolved"
required_scripts=(process_threads_metric_jobs.py)
[[ "$health_check" != true ]] || required_scripts+=(check_autonomous_health.py)
[[ "$strategy_apply" != true && "$feedback_preview" != true ]] || required_scripts+=(run_growth_attribution_cycle.py)
[[ "$ready_bank_reuse" != true && "$feedback_preview" != true ]] || required_scripts+=(maintain_text_ready_inventory.py)
for script in "${required_scripts[@]}"; do
  [[ -f "$release/scripts/$script" && ! -L "$release/scripts/$script" ]] || {
    echo "[BLOCKED] required immutable aftercare script missing or linked" >&2; exit 78;
  }
done
[[ -d "$runtime_root/shared" && ! -L "$runtime_root/shared" &&
   -f "$runtime_env" && ! -L "$runtime_env" ]] || {
  echo "[BLOCKED] protected runtime environment missing or linked" >&2
  exit 78
}
permissions="$(stat -c '%a' "$runtime_env" 2>/dev/null || stat -f '%Lp' "$runtime_env")"
owner_uid="$(stat -c '%u' "$runtime_env" 2>/dev/null || stat -f '%u' "$runtime_env")"
[[ "$permissions" == 600 && ( "$owner_uid" == "$EUID" || "$owner_uid" == 0 ) ]] || {
  echo "[BLOCKED] runtime environment must have 0600 permissions" >&2
  exit 77
}

# Read the write gate ONLY from protected runtime config, not the caller's
# process environment. No credential contents are emitted.
unset AFTERCARE_METRICS_WRITE_APPROVED
unset AFTERCARE_ACTIONS_DISABLED_ATTESTED
unset AFTERCARE_STRATEGY_WRITE_APPROVED
unset AFTERCARE_READY_BANK_REUSE_APPROVED
unset AFTERCARE_BEAUTY_METRICS_APPROVED BEAUTY_ACTIVATION_APPROVED BEAUTY_PRODUCTION_ENABLED
unset GCP_SA_JSON_BASE64 SA_JSON_BASE64 GCP_SA_JSON GOOGLE_APPLICATION_CREDENTIALS
unset SPREADSHEET_ID SNS_MASTER_SHEET_ID NOTE_MASTER_SHEET_ID
unset PYTHONPATH PYTHONHOME THREADS_TOKEN_STORE_DIR THREADS_APP_ID THREADS_APP_SECRET
for scope in NIGHT_SCOUT LIVER_MANAGER BEAUTY_ACCOUNT; do
  unset "THREADS_ACCESS_TOKEN_$scope" "THREADS_USER_ID_$scope" "THREADS_HANDLE_$scope"
  unset "THREADS_APP_ID_$scope" "THREADS_APP_SECRET_$scope"
done
set -a
# shellcheck disable=SC1090
source "$runtime_env"
set +a
[[ -n "${SA_JSON_BASE64:-}${GCP_SA_JSON_BASE64:-}${GCP_SA_JSON:-}" &&
   -n "${SPREADSHEET_ID:-}${SNS_MASTER_SHEET_ID:-}${NOTE_MASTER_SHEET_ID:-}" ]] || {
  echo "[BLOCKED] protected Sheets configuration missing" >&2; exit 78;
}
export BEAUTY_PRODUCTION_ENABLED=false
if [[ "$account" == beauty_account ]]; then
  [[ "${BEAUTY_ACTIVATION_APPROVED:-false}" == true &&
     "${AFTERCARE_BEAUTY_METRICS_APPROVED:-false}" == true ]] || {
    echo "[BLOCKED] independent protected Beauty activation and metrics approval required" >&2; exit 77;
  }
  export BEAUTY_PRODUCTION_ENABLED=true
fi
if [[ "$mode" == "apply" && "${AFTERCARE_METRICS_WRITE_APPROVED:-false}" != true ]]; then
  echo "[BLOCKED] independent metrics write approval is not enabled" >&2
  exit 77
fi
if [[ "$mode" == "apply" && "${AFTERCARE_ACTIONS_DISABLED_ATTESTED:-false}" != true ]]; then
  echo "[BLOCKED] competing Actions aftercare scheduling is not attested disabled" >&2
  exit 77
fi
if [[ "$strategy_apply" == true && "${AFTERCARE_STRATEGY_WRITE_APPROVED:-false}" != true ]]; then
  echo "[BLOCKED] separate measured-strategy write approval is missing" >&2
  exit 77
fi
if [[ "$ready_bank_reuse" == true && "${AFTERCARE_READY_BANK_REUSE_APPROVED:-false}" != true ]]; then
  echo "[BLOCKED] separate zero-AI READY bank reuse approval is missing" >&2
  exit 77
fi

# Both modes must never publish, generate/transform third-party media, or
# use a paid text-generation API. They only use the existing metrics worker.
export PUBLISH_ENABLED=false
export ALLOW_REAL_THREADS_POST=false
export ALLOW_REAL_THREADS_VIDEO_POST=false
export ALLOW_REAL_X_POST=false
export ALLOW_MEDIA_POSTS=false
export ALLOW_CLOUDINARY_UPLOAD=false
export ALLOW_VIDEO_DOWNLOAD=false
export ALLOW_VIDEO_CUT=false
export ALLOW_TRANSCRIPTION_API=false
export GEMINI_API_KEY=""
export GOOGLE_API_KEY=""
export OPENAI_API_KEY=""
export ANTHROPIC_API_KEY=""
export GITHUB_MODELS_API_KEY=""
export GITHUB_TOKEN=""
export GH_TOKEN=""
export GITHUB_MODELS_TOKEN=""
export GITHUB_MODELS_ENABLED=false
export MOCK_LLM=false MOCK_SHEETS=false DRY_RUN=false
export ALLOW_LOCAL_TRANSCRIPTION=false ALLOW_THREADS_CAROUSEL=false ALLOW_THREADS_MIXED_CAROUSEL=false
export DELIVERY_ENGINE=buffered_vps
export PRODUCTION_TRIGGER="$trigger"
export CODE_REVISION="$revision"
export PRODUCTION_RUNTIME_RELEASE="$release"

# Reuse the posting runtime's shared Sheets and account lock directory.
# This tool does not create or install the directory on the VPS.
[[ -d "$locks" && ! -L "$locks" ]] || {
  echo "[BLOCKED] shared account and Sheets locks are unavailable" >&2
  exit 78
}
sheet_lock="$locks/sheets-io.lock"
account_lock="$locks/$account.lock"
[[ ! -L "$sheet_lock" && ! -L "$account_lock" ]] || {
  echo "[BLOCKED] Sheets or account lock is a symlink" >&2
  exit 78
}
# Keep BOTH locks over the entire plan/apply/feedback lifecycle. This
# prevents a publisher or another account job from mutating the shared
# operational workbook between a read-only plan and its write decision.
# The previous wrapper reacquired each lock separately for every step,
# leaving a race window.
exec 9>"$sheet_lock"
flock -w 240 9 || {
  echo "[BLOCKED] shared Sheets quota lock is busy" >&2
  exit 75
}
exec 7>"$account_lock"
flock -n -E 75 7 || {
  echo "[BLOCKED] account aftercare lock is busy" >&2
  exit 75
}

# Child diagnostics can include unpublished IDs or provider errors. Keep them
# in a private temporary directory; only fixed stage receipts reach public logs.
scratch="$(mktemp -d "$runtime_root/shared/aftercare.XXXXXX")"
cleanup() { [[ -z "$scratch" ]] || rm -rf -- "$scratch"; }
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
cd "$release"
run_stage() {
  local stage="$1"
  shift
  local code
  if timeout 35m "$release/.venv/bin/python" "$@" > "$scratch/$stage.stdout" 2> "$scratch/$stage.stderr"; then
    echo "[OK] aftercare stage=$stage"
  else
    code=$?
    echo "[BLOCKED] aftercare stage=$stage exit=$code; no automatic retry" >&2
    return "$code"
  fi
}

# A read-only plan touches the provider only AFTER acquiring shared locks.
# An apply first produces a read-only plan, then performs at most one bounded
# metric-job invocation. All IDs and results come from the trusted workbooks.
# A non-zero plan/collector exit aborts, never auto-retries unknown writes.
run_stage metrics_preview \
  "$release/scripts/process_threads_metric_jobs.py" \
  --account-id "$account" --max-jobs 20 --dry-run --use-sheets

if [[ "$mode" == "apply" ]]; then
  run_stage metrics_apply \
    "$release/scripts/process_threads_metric_jobs.py" \
    --account-id "$account" --max-jobs 20 --apply --confirm-metrics --use-sheets
  echo "[OK] bounded metrics write attempt completed; no blind retry"
fi

# The two optional downstream write stages are manual canaries only.
# They share the *same locks and pinned immutable release*. Each stage
# performs strict account/scope/row/receipt verification of its own.
# There is NO automatic retry or rollback across Google operations.
if [[ "$strategy_apply" == true ]]; then
  [[ -f "$release/scripts/run_growth_attribution_cycle.py" ]] || {
    echo "[BLOCKED] attribution writer absent from pinned release" >&2
    exit 78
  }
  run_stage strategy_apply \
    "$release/scripts/run_growth_attribution_cycle.py" \
    --account-id "$account" --apply --confirm-attribution --use-sheets \
    --max-write-rows 120 || {
    echo "[BLOCKED] strategy delivery unknown/failed; do not retry blindly" >&2
    exit 1
  }
  echo "[OK] measured strategy apply returned verified outcome"
fi
if [[ "$ready_bank_reuse" == true ]]; then
  [[ -f "$release/scripts/maintain_text_ready_inventory.py" ]] || {
    echo "[BLOCKED] READY bank writer absent from pinned release" >&2
    exit 78
  }
  # This code path CANNOT call replenish()/Gemini or create new content.
  # Only previously approved evergreen candidates are eligible.
  run_stage ready_reuse \
    "$release/scripts/maintain_text_ready_inventory.py" \
    --account-id "$account" --apply --confirm-ready-maintenance \
    --use-sheets --reuse-only \
    --max-bank-allocations "$bank_allocations" || {
    echo "[BLOCKED] READY bank reuse incomplete/unknown; do not retry blindly" >&2
    exit 1
  }
  echo "[OK] bounded zero-AI READY bank reuse completed"
fi

# Continue the existing data->insights->next-inventory loop in *preview*
# mode ONLY. Attribution remains strictly read-only, no strategy_state
# persistence or prompt mutation; READY inspection cannot generate posts,
# consume AI/Gemini budget, allocate evergreen, or promote queue status.
# A failed preview after applied metrics means PARTIAL aftercare, NOT rollback.
if [[ "$feedback_preview" == true ]]; then
  [[ -f "$release/scripts/run_growth_attribution_cycle.py" &&
     -f "$release/scripts/maintain_text_ready_inventory.py" ]] || {
    echo "[BLOCKED] feedback-preview scripts missing from release" >&2
    exit 78
  }
  run_stage attribution_preview \
    "$release/scripts/run_growth_attribution_cycle.py" \
    --account-id "$account" --dry-run --use-sheets || {
    echo "[BLOCKED] measured attribution preview failed; no auto retry" >&2
    exit 1
  }
  run_stage inventory_preview \
    "$release/scripts/maintain_text_ready_inventory.py" \
    --account-id "$account" --dry-run --use-sheets || {
    echo "[BLOCKED] next text-READY coverage degraded; no generation started" >&2
    exit 1
  }
  echo "[OK] read-only attribution + next-text inventory previews complete"
fi
if [[ "$health_check" == true ]]; then
  # Readability and account binding are checked separately from the legacy
  # advisory health report. A failed read cannot become a successful stage.
  run_stage runtime_health \
    "$release/scripts/check_autonomous_health.py" \
    --account-id "$account" --dry-run --use-sheets --strict-runtime
fi
echo "[OK] aftercare mode=$mode account=$account posts=false hosted_workflow_equivalent=false"
