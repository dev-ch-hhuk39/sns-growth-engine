#!/usr/bin/env bash
# Xserver primary, bounded media inventory replenishment entrypoint.
set -euo pipefail

RUNTIME_ROOT="${BUFFERED_RUNTIME_ROOT:-/opt/github-runners/sns-growth-engine/.buffered-runtime}"
CURRENT_RELEASE="${RUNTIME_ROOT}/current"
RUNTIME_ENV_FILE="${BUFFERED_RUNTIME_ENV_FILE:-${RUNTIME_ROOT}/shared/runtime.env}"

if [[ ! -x "$CURRENT_RELEASE/.venv/bin/python" || ! -f "$CURRENT_RELEASE/.production-release" ]]; then
  echo '[BLOCKED] immutable production release or media runtime is not installed' >&2
  exit 78
fi
if [[ ! -f "$RUNTIME_ENV_FILE" ]]; then
  echo '[BLOCKED] production runtime environment is not installed' >&2
  exit 78
fi
mode="$(stat -c '%a' "$RUNTIME_ENV_FILE" 2>/dev/null || stat -f '%Lp' "$RUNTIME_ENV_FILE")"
if [[ "$mode" != '600' ]]; then
  echo '[BLOCKED] production runtime environment permissions must be 0600' >&2
  exit 77
fi

set -a
# shellcheck disable=SC1090
source "$RUNTIME_ENV_FILE"
set +a

export BUFFERED_RUNTIME_ROOT="$RUNTIME_ROOT"
export PRODUCTION_RUNTIME_RELEASE="$CURRENT_RELEASE"
export PRODUCTION_HOST_EXECUTION_ID="xserver_media_prep_$(date -u +%Y%m%dT%H%M%SZ)_$$"
export PATH="$CURRENT_RELEASE/.venv/bin:$RUNTIME_ROOT/shared/threads-cli:/opt/sns-node-v22.23.2/bin:/usr/local/bin:/usr/bin:/bin"
export SNS_YTDLP_NODE_PATH=/opt/sns-node-v22.23.2/bin/node

# Publishing is never part of this entrypoint, including after runtime.env is
# sourced. The Python runner enables only temporary download/cut/upload gates
# for its exact prepare-only child command.
export PUBLISH_ENABLED=false ALLOW_REAL_THREADS_POST=false ALLOW_REAL_THREADS_VIDEO_POST=false
export ALLOW_MEDIA_POSTS=false ALLOW_THREADS_CAROUSEL=false ALLOW_REAL_X_POST=false
export ALLOW_VIDEO_DOWNLOAD=false ALLOW_VIDEO_CUT=false ALLOW_CLOUDINARY_UPLOAD=false
export ALLOW_TRANSCRIPTION_API=false ALLOW_LOCAL_TRANSCRIPTION=false GITHUB_MODELS_ENABLED=false

exec "$CURRENT_RELEASE/.venv/bin/python" "$CURRENT_RELEASE/scripts/run_buffered_media_preparation_host.py" \
  --apply --confirm-preparation
