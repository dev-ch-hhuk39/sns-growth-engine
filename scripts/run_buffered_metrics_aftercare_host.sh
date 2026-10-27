#!/usr/bin/env bash
# Action-free 24h / 72h / 168h Threads metrics-aftercare entrypoint.
#
# Source only: do not install cron or invoke real providers in development.
# Operator/VPS Ops owns protected configuration and the production schedule.
# `--plan` is fully offline and never reads runtime credentials.
set +x
set -euo pipefail

account=""
mode="plan"
confirmed_readonly="false"
confirmed_metrics="false"
feedback_preview="false"
strategy_apply="false"
ready_bank_reuse="false"
bank_allocations=2
trigger="manual"

usage() {
  echo "usage: $0 --account-id <night_scout|liver_manager> [--plan | --dry-run --confirm-readonly | --apply --confirm-metrics] [--with-feedback-preview] [--with-strategy-apply] [--with-ready-bank-reuse] [--max-bank-allocations 0..6] [--trigger manual|xserver_cron]" >&2
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

# This is deliberately narrower than the general publisher account registry:
# Beauty requires separate owner authorization and must not be silently added.
case "$account" in
  night_scout|liver_manager) ;;
  *) usage; exit 64 ;;
esac
case "$trigger" in
  manual|xserver_cron) ;;
  *) usage; exit 64 ;;
esac
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
  printf '{"status":"PLAN_ONLY","account_id":"%s","trigger":"%s","stage":"metrics_24_72_168","feedback_preview":%s,"feedback_stages":["measured_attribution","next_text_ready_coverage"],"would_connect":false,"would_write":false,"would_post":false,"github_actions_used":false}\n' "$account" "$trigger" "$feedback_preview"
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
runtime_env="${BUFFERED_RUNTIME_ENV_FILE:-$runtime_root/shared/runtime.env}"
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
[[ -f "$runtime_env" && ! -L "$runtime_env" ]] || {
  echo "[BLOCKED] protected runtime environment missing or linked" >&2
  exit 78
}
permissions="$(stat -c '%a' "$runtime_env" 2>/dev/null || stat -f '%Lp' "$runtime_env")"
[[ "$permissions" == 600 ]] || {
  echo "[BLOCKED] runtime environment must have 0600 permissions" >&2
  exit 77
}

# Read the write gate ONLY from protected runtime config, not the caller's
# process environment. No credential contents are emitted.
unset AFTERCARE_METRICS_WRITE_APPROVED
unset AFTERCARE_ACTIONS_DISABLED_ATTESTED
unset AFTERCARE_STRATEGY_WRITE_APPROVED
unset AFTERCARE_READY_BANK_REUSE_APPROVED
set -a
# shellcheck disable=SC1090
source "$runtime_env"
set +a
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
export DELIVERY_ENGINE=buffered_vps
export PRODUCTION_TRIGGER="$trigger"
export CODE_REVISION="$revision"

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

# A read-only plan touches the provider only AFTER acquiring shared locks.
# An apply first produces a read-only plan, then performs at most one bounded
# metric-job invocation. All IDs and results come from the trusted workbooks.
# A non-zero plan/collector exit aborts, never auto-retries unknown writes.
timeout 35m "$release/.venv/bin/python" \
  "$release/scripts/process_threads_metric_jobs.py" \
  --account-id "$account" --max-jobs 20 --dry-run --use-sheets

if [[ "$mode" == "apply" ]]; then
  timeout 35m "$release/.venv/bin/python" \
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
  timeout 35m "$release/.venv/bin/python" \
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
  timeout 35m "$release/.venv/bin/python" \
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
  timeout 35m "$release/.venv/bin/python" \
    "$release/scripts/run_growth_attribution_cycle.py" \
    --account-id "$account" --dry-run --use-sheets || {
    echo "[BLOCKED] measured attribution preview failed; no auto retry" >&2
    exit 1
  }
  timeout 35m "$release/.venv/bin/python" \
    "$release/scripts/maintain_text_ready_inventory.py" \
    --account-id "$account" --dry-run --use-sheets || {
    echo "[BLOCKED] next text-READY coverage degraded; no generation started" >&2
    exit 1
  }
  echo "[OK] read-only attribution + next-text inventory previews complete"
fi
echo "[OK] aftercare mode=$mode account=$account; no SNS publish attempted"
