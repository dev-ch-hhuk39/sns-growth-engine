#!/usr/bin/env bash
# Source-only, bounded X/YouTube metadata acquisition; no scheduler installation.
# Default --plan is offline and does not inspect a release or runtime credentials.
# Threads/TikTok and the complete hosted Beauty corpus path remain deferred.
set +x
set -euo pipefail
umask 077

account=""
scope=""
platform=""
mode="plan"
mode_selected=false
confirmed=false
max_posts=3
trigger=manual

usage() {
  echo "usage: $0 --account-id <night_scout|liver_manager|beauty_account> --scope <approved|reference-only> --platform <x|youtube> [--max-posts 1..30] [--plan | --apply --confirm-acquisition] [--trigger manual|xserver_cron]" >&2
}
while [[ $# -gt 0 ]]; do
  case "$1" in
    --account-id|--scope|--platform|--max-posts|--trigger)
      [[ $# -ge 2 ]] || { usage; exit 64; }
      case "$1" in
        --account-id) [[ -z "$account" ]] || { usage; exit 64; }; account="$2" ;;
        --scope) [[ -z "$scope" ]] || { usage; exit 64; }; scope="$2" ;;
        --platform) [[ -z "$platform" ]] || { usage; exit 64; }; platform="$2" ;;
        --max-posts) max_posts="$2" ;;
        --trigger) trigger="$2" ;;
      esac
      shift 2 ;;
    --plan|--apply)
      [[ "$mode_selected" == false ]] || { usage; exit 64; }
      mode="${1#--}"; mode_selected=true; shift ;;
    --confirm-acquisition)
      [[ "$confirmed" == false ]] || { usage; exit 64; }
      confirmed=true; shift ;;
    *) usage; exit 64 ;;
  esac
done
case "$account" in night_scout|liver_manager|beauty_account) ;; *) usage; exit 64 ;; esac
case "$scope" in approved|reference-only) ;; *) usage; exit 64 ;; esac
case "$platform" in x|youtube) ;; *) usage; exit 64 ;; esac
case "$trigger" in manual|xserver_cron) ;; *) usage; exit 64 ;; esac
[[ "$max_posts" =~ ^([1-9]|[12][0-9]|30)$ ]] || {
  echo "[BLOCKED] per-source scan cap must be 1..30" >&2; exit 64;
}
if [[ "$account" == beauty_account && "$scope" != reference-only ]]; then
  echo "[BLOCKED] Beauty acquisition requires its separate reference-only scope" >&2
  exit 64
fi
if [[ "$mode" == plan ]]; then
  [[ "$confirmed" == false ]] || {
    echo "[BLOCKED] confirmation requires explicit --apply" >&2; exit 64;
  }
  reference_arg=""
  [[ "$scope" != reference-only ]] || reference_arg=',"--reference-only"'
  printf '{"status":"PLAN_ONLY","account_id":"%s","scope":"%s","platform":"%s","max_posts_per_source":%s,"trigger":"%s","stage":"source_post_metadata_acquisition","command":["<immutable-release>/.venv/bin/python","<immutable-release>/scripts/acquire_approved_source_posts_failsoft.py","--account-id","%s","--platform","%s","--max-posts","%s"%s,"--dry-run"],"would_connect":false,"would_write":false,"would_post":false,"physical_media":false,"hosted_workflow_parity":false,"github_actions_used":false}\n' \
    "$account" "$scope" "$platform" "$max_posts" "$trigger" \
    "$account" "$platform" "$max_posts" "$reference_arg"
  exit 0
fi
[[ "$confirmed" == true ]] || {
  echo "[BLOCKED] --apply requires --confirm-acquisition" >&2; exit 64;
}

runtime_root="${BUFFERED_RUNTIME_ROOT:-/opt/github-runners/sns-growth-engine/.buffered-runtime}"
[[ "$runtime_root" = /* && "$runtime_root" != */ ]] || {
  echo "[BLOCKED] runtime root must be absolute without a trailing slash" >&2; exit 78;
}
# A caller cannot substitute a second file as an independent consent source.
runtime_env="$runtime_root/shared/runtime.env"
locks="$runtime_root/shared/locks"
shared_deploy_lock="/run/lock/chadult-production-deploy.lock"
[[ -f "$shared_deploy_lock" && ! -L "$shared_deploy_lock" && -w "$shared_deploy_lock" ]] || {
  echo "[BLOCKED] shared deployment lock is unavailable" >&2; exit 78;
}
exec 8<>"$shared_deploy_lock"
flock -s -w 120 8 || {
  echo "[BLOCKED] deployment currently holds the shared lock" >&2; exit 75;
}

# Resolve only after the deployment lock. All subsequent reads and execution
# use this exact releases/<SHA> directory, never the mutable current symlink.
[[ -L "$runtime_root/current" ]] || {
  echo "[BLOCKED] immutable acquisition release is not installed" >&2; exit 78;
}
release="$(readlink -f "$runtime_root/current")"
revision="${release##*/}"
[[ "$revision" =~ ^[0-9a-f]{40}$ && "$release" == "$runtime_root/releases/$revision" &&
   -d "$release" && ! -L "$release" &&
   -f "$release/.production-release" && ! -L "$release/.production-release" &&
   -f "$release/scripts/acquire_approved_source_posts.py" &&
   ! -L "$release/scripts/acquire_approved_source_posts.py" &&
   -f "$release/scripts/acquire_approved_source_posts_failsoft.py" &&
   ! -L "$release/scripts/acquire_approved_source_posts_failsoft.py" &&
   -x "$release/.venv/bin/python" ]] || {
  echo "[BLOCKED] invalid immutable acquisition release" >&2; exit 78;
}
[[ "$(cat "$release/.production-release")" == "$revision" ]] || {
  echo "[BLOCKED] immutable acquisition release marker mismatch" >&2; exit 78;
}
[[ -d "$runtime_root/shared" && ! -L "$runtime_root/shared" &&
   -f "$runtime_env" && ! -L "$runtime_env" ]] || {
  echo "[BLOCKED] protected runtime environment is missing or linked" >&2; exit 78;
}
permissions="$(stat -c '%a' "$runtime_env" 2>/dev/null || stat -f '%Lp' "$runtime_env")"
owner_uid="$(stat -c '%u' "$runtime_env" 2>/dev/null || stat -f '%u' "$runtime_env")"
[[ "$permissions" == 600 && ( "$owner_uid" == "$EUID" || "$owner_uid" == 0 ) ]] || {
  echo "[BLOCKED] runtime environment must be owner-protected 0600" >&2; exit 77;
}

# CLI and inherited environment values never grant consent. The protected
# host configuration must approve this exact account, scope, platform and SHA.
unset ACQUISITION_WRITE_APPROVED ACQUISITION_ACTIONS_DISABLED_ATTESTED
unset ACQUISITION_APPROVED_ACCOUNT ACQUISITION_APPROVED_SCOPE
unset ACQUISITION_APPROVED_PLATFORM ACQUISITION_APPROVED_RELEASE
unset BEAUTY_ACTIVATION_APPROVED BEAUTY_PRODUCTION_ENABLED
unset GCP_SA_JSON_BASE64 SA_JSON_BASE64 GCP_SA_JSON
unset SPREADSHEET_ID SNS_MASTER_SHEET_ID NOTE_MASTER_SHEET_ID GOOGLE_APPLICATION_CREDENTIALS
unset PYTHONPATH PYTHONHOME
set -a
# shellcheck disable=SC1090
source "$runtime_env"
set +a
[[ "${ACQUISITION_WRITE_APPROVED:-false}" == true &&
   "${ACQUISITION_ACTIONS_DISABLED_ATTESTED:-false}" == true ]] || {
  echo "[BLOCKED] independent acquisition write consent or scheduler attestation is missing" >&2
  exit 77
}
[[ "${ACQUISITION_APPROVED_ACCOUNT:-}" == "$account" &&
   "${ACQUISITION_APPROVED_SCOPE:-}" == "$scope" &&
   "${ACQUISITION_APPROVED_PLATFORM:-}" == "$platform" &&
   "${ACQUISITION_APPROVED_RELEASE:-}" == "$revision" ]] || {
  echo "[BLOCKED] protected acquisition account/scope/platform/release consent mismatch" >&2
  exit 77
}
[[ -n "${SA_JSON_BASE64:-}${GCP_SA_JSON_BASE64:-}${GCP_SA_JSON:-}" &&
   -n "${SPREADSHEET_ID:-}${SNS_MASTER_SHEET_ID:-}${NOTE_MASTER_SHEET_ID:-}" ]] || {
  echo "[BLOCKED] protected Sheets configuration is missing" >&2; exit 78;
}
export BEAUTY_PRODUCTION_ENABLED=false
if [[ "$account" == beauty_account ]]; then
  case "${BEAUTY_ACTIVATION_APPROVED:-false}" in
    1|true|TRUE|yes|YES) export BEAUTY_PRODUCTION_ENABLED=true ;;
    *) echo "[BLOCKED] independent Beauty activation approval is missing" >&2; exit 77 ;;
  esac
fi

# These are metadata-only adapters: X gallery-dl uses --no-download and
# YouTube yt-dlp discovery/detail use skip_download + download=False.
# Reuse rights still come from the existing source/author/permission ledger;
# reference-only never grants media rights. No media preparation is invoked.
export PUBLISH_ENABLED=false ALLOW_REAL_THREADS_POST=false ALLOW_REAL_X_POST=false
export ALLOW_REAL_THREADS_VIDEO_POST=false ALLOW_MEDIA_POSTS=false
export ALLOW_THREADS_CAROUSEL=false ALLOW_THREADS_MIXED_CAROUSEL=false
export ALLOW_VIDEO_DOWNLOAD=false ALLOW_VIDEO_CUT=false ALLOW_CLOUDINARY_UPLOAD=false
export ALLOW_TRANSCRIPTION_API=false ALLOW_LOCAL_TRANSCRIPTION=false
export GEMINI_API_KEY=""
export GOOGLE_API_KEY=""
export OPENAI_API_KEY=""
export ANTHROPIC_API_KEY=""
export FIRECRAWL_API_KEY=""
export DELIVERY_ENGINE=buffered_vps PRODUCTION_TRIGGER="$trigger" CODE_REVISION="$revision"
export PRODUCTION_RUNTIME_RELEASE="$release"

[[ -d "$locks" && ! -L "$locks" ]] || {
  echo "[BLOCKED] shared Sheets/account lock directory is unavailable" >&2; exit 78;
}
sheet_lock="$locks/sheets-io.lock"
account_lock="$locks/$account.lock"
[[ ! -L "$sheet_lock" && ! -L "$account_lock" ]] || {
  echo "[BLOCKED] Sheets or account lock is linked" >&2; exit 78;
}
exec 9>"$sheet_lock"
flock -w 240 9 || {
  echo "[BLOCKED] shared Sheets lock is busy" >&2; exit 75;
}
exec 7>"$account_lock"
flock -n -E 75 7 || {
  echo "[BLOCKED] account acquisition lock is busy" >&2; exit 75;
}

args=(--account-id "$account" --platform "$platform" --max-posts "$max_posts")
[[ "$scope" != reference-only ]] || args+=(--reference-only)
# The plan and bounded mutation use the same pinned release and all three
# locks. Critical persistence/readback errors remain nonzero; telemetry alone
# may degrade under the existing failsoft CLI contract. No wrapper retry.
timeout 35m "$release/.venv/bin/python" \
  "$release/scripts/acquire_approved_source_posts_failsoft.py" "${args[@]}" --dry-run
if timeout 35m "$release/.venv/bin/python" \
  "$release/scripts/acquire_approved_source_posts_failsoft.py" "${args[@]}" \
  --apply --confirm-acquisition; then
  echo "[OK] bounded metadata acquisition completed; no SNS or physical media operation"
else
  code=$?
  echo "[BLOCKED] acquisition incomplete/unknown; do not retry blindly" >&2
  exit "$code"
fi
