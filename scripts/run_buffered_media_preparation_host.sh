#!/usr/bin/env bash
# Xserver primary, bounded media inventory replenishment entrypoint.
# Source only: installs no timer and grants no new media operation approval.
set +x
set -euo pipefail
umask 077

RUNTIME_ROOT="${BUFFERED_RUNTIME_ROOT:-/opt/github-runners/sns-growth-engine/.buffered-runtime}"
[[ "$RUNTIME_ROOT" = /* && "$RUNTIME_ROOT" != */ && "$RUNTIME_ROOT" != *$'\n'* ]] || {
  echo '[BLOCKED] absolute media runtime root without trailing slash required' >&2; exit 78;
}
CURRENT_RELEASE="${RUNTIME_ROOT}/current"
# A process caller cannot replace the independently protected host source.
RUNTIME_ENV_FILE="${RUNTIME_ROOT}/shared/runtime.env"

# A 1.9 GiB shared host previously OOM-killed SNS Python and unrelated
# Next.js services. Keep the existing resource floor before loading any
# runtime credentials or invoking the media runner. Deferral is not success
# evidence for media inventory or a replacement scheduler.
mem_total_kib="$(awk '/^MemTotal:/ {print $2}' /proc/meminfo 2>/dev/null || true)"
mem_available_kib="$(awk '/^MemAvailable:/ {print $2}' /proc/meminfo 2>/dev/null || true)"
if [[ ! "$mem_total_kib" =~ ^[0-9]+$ || ! "$mem_available_kib" =~ ^[0-9]+$ ||
      "$mem_total_kib" -lt 4194304 || "$mem_available_kib" -lt 1572864 ]]; then
  echo '[DEFERRED] VPS media preparation requires >=4 GiB RAM and >=1.5 GiB MemAvailable; GitHub-hosted fallback remains responsible' >&2
  exit 0
fi
common_lock=/run/lock/chadult-production-deploy.lock
[[ -f "$common_lock" && ! -L "$common_lock" && -w "$common_lock" ]] || {
  echo '[BLOCKED] common deployment lock unavailable for heavy media preparation' >&2; exit 78;
}
exec 8<>"$common_lock"
flock -s -w 120 8 || { echo '[BLOCKED] deployment in progress; defer media preparation' >&2; exit 75; }

# Resolve only AFTER acquiring the global lock. All reads and execution use
# this exact immutable directory, never the mutable current pointer again.
[[ -L "$CURRENT_RELEASE" ]] || {
  echo '[BLOCKED] immutable production release pointer is not installed' >&2; exit 78;
}
resolved="$(readlink -f "$CURRENT_RELEASE")"
revision="${resolved##*/}"
[[ "$revision" =~ ^[0-9a-f]{40}$ && "$resolved" == "$RUNTIME_ROOT/releases/$revision" &&
   -d "$resolved" && ! -L "$resolved" &&
   -f "$resolved/.production-release" && ! -L "$resolved/.production-release" &&
   -f "$resolved/scripts/run_buffered_media_preparation_host.py" &&
   ! -L "$resolved/scripts/run_buffered_media_preparation_host.py" &&
   -x "$resolved/.venv/bin/python" ]] || {
  echo '[BLOCKED] immutable production release or media runtime is not installed' >&2; exit 78;
}
[[ "$(cat "$resolved/.production-release")" == "$revision" ]] || {
  echo '[BLOCKED] immutable media release marker mismatch' >&2; exit 78;
}
CURRENT_RELEASE="$resolved"
[[ -d "$RUNTIME_ROOT/shared" && ! -L "$RUNTIME_ROOT/shared" &&
   -f "$RUNTIME_ENV_FILE" && ! -L "$RUNTIME_ENV_FILE" ]] || {
  echo '[BLOCKED] protected production runtime environment is missing or linked' >&2; exit 78;
}
mode="$(stat -c '%a' "$RUNTIME_ENV_FILE" 2>/dev/null || stat -f '%Lp' "$RUNTIME_ENV_FILE")"
owner_uid="$(stat -c '%u' "$RUNTIME_ENV_FILE" 2>/dev/null || stat -f '%u' "$RUNTIME_ENV_FILE")"
[[ "$mode" == 600 && ( "$owner_uid" == "$EUID" || "$owner_uid" == 0 ) ]] || {
  echo '[BLOCKED] production runtime environment must be owner-protected 0600' >&2; exit 77;
}

# Load supported connection aliases and approvals only from the validated
# protected source. Caller keys, import hooks, Beauty grants and alternate
# token/budget directories cannot substitute for missing host configuration.
unset GCP_SA_JSON_BASE64 SA_JSON_BASE64 GCP_SA_JSON GOOGLE_APPLICATION_CREDENTIALS
unset SPREADSHEET_ID SNS_MASTER_SHEET_ID NOTE_MASTER_SHEET_ID
unset CLOUDINARY_CLOUD_NAME CLOUDINARY_API_KEY CLOUDINARY_API_SECRET
unset GEMINI_API_KEY GOOGLE_API_KEY OPENAI_API_KEY ANTHROPIC_API_KEY FIRECRAWL_API_KEY
unset BEAUTY_ACTIVATION_APPROVED BEAUTY_PRODUCTION_ENABLED
unset PYTHONPATH PYTHONHOME THREADS_TOKEN_STORE_DIR
unset SNS_HOST_AI_BUDGET_REQUIRED SNS_HOST_AI_BUDGET_DIR SNS_HOST_AI_RUN_ID SNS_HOST_AI_ACCOUNT_ID SNS_HOST_AI_RELEASE
set -a
# shellcheck disable=SC1090
source "$RUNTIME_ENV_FILE"
set +a
[[ -n "${SA_JSON_BASE64:-}${GCP_SA_JSON_BASE64:-}${GCP_SA_JSON:-}" &&
   -n "${SPREADSHEET_ID:-}${SNS_MASTER_SHEET_ID:-}${NOTE_MASTER_SHEET_ID:-}" &&
   -n "${CLOUDINARY_CLOUD_NAME:-}" && -n "${CLOUDINARY_API_KEY:-}" &&
   -n "${CLOUDINARY_API_SECRET:-}" && -n "${GEMINI_API_KEY:-}" ]] || {
  echo '[BLOCKED] protected media runtime credentials are incomplete' >&2; exit 78;
}

export BUFFERED_RUNTIME_ROOT="$RUNTIME_ROOT"
export PRODUCTION_RUNTIME_RELEASE="$CURRENT_RELEASE"
export CODE_REVISION="$revision"
export PRODUCTION_HOST_EXECUTION_ID="xserver_media_prep_$(date -u +%Y%m%dT%H%M%SZ)_$$"
export PATH="$CURRENT_RELEASE/.venv/bin:$RUNTIME_ROOT/shared/threads-cli:/opt/sns-node-v22.23.2/bin:/usr/local/bin:/usr/bin:/bin"
export SNS_YTDLP_NODE_PATH=/opt/sns-node-v22.23.2/bin/node

# Publishing is never part of this entrypoint, including after runtime.env is
# sourced. The Python runner retains all existing policy/rights/resource
# checks and enables temporary download/cut/upload gates only for its exact
# prepare-only children. Mock configuration cannot establish live evidence.
export PUBLISH_ENABLED=false ALLOW_REAL_THREADS_POST=false ALLOW_REAL_THREADS_VIDEO_POST=false
export ALLOW_MEDIA_POSTS=false ALLOW_THREADS_CAROUSEL=false ALLOW_THREADS_MIXED_CAROUSEL=false ALLOW_REAL_X_POST=false
export ALLOW_VIDEO_DOWNLOAD=false ALLOW_VIDEO_CUT=false ALLOW_CLOUDINARY_UPLOAD=false
export ALLOW_TRANSCRIPTION_API=false ALLOW_LOCAL_TRANSCRIPTION=false GITHUB_MODELS_ENABLED=false
export MOCK_LLM=false MOCK_SHEETS=false DRY_RUN=false
export GITHUB_TOKEN=""
export GH_TOKEN=""
export GITHUB_MODELS_TOKEN=""
export GITHUB_MODELS_API_KEY=""
cd "$CURRENT_RELEASE"
exec "$CURRENT_RELEASE/.venv/bin/python" "$CURRENT_RELEASE/scripts/run_buffered_media_preparation_host.py" \
  --apply --confirm-preparation
