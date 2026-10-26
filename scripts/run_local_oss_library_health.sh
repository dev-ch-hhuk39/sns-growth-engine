#!/bin/bash
# Weekly read-only public research tool checks on the authorized Mac.
set -euo pipefail
umask 077
ROOT=/Users/hayatoa/Projects/sns-growth-engine-bank-acceptance-20261024
STATE="$HOME/.cache/chadult-sns-oss-health"
PIN=249c7a4c040558a903d6838dee31012980d4946d
PY="$STATE/.venv/bin/python"
PREFLIGHT_PY=/Library/Frameworks/Python.framework/Versions/3.13/bin/python3
PATH="$STATE/.venv/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
export PATH
unset GH_TOKEN GITHUB_TOKEN OPENAI_API_KEY ANTHROPIC_API_KEY GOOGLE_API_KEY
unset SA_JSON_BASE64 GCP_SA_JSON_BASE64 SNS_MASTER_SHEET_ID SPREADSHEET_ID
unset PUBLISH_ENABLED ALLOW_REAL_THREADS_POST ALLOW_MEDIA_POSTS
export PUBLISH_ENABLED=false ALLOW_REAL_THREADS_POST=false ALLOW_MEDIA_POSTS=false
export PYTHONPATH="$ROOT/src:$ROOT/scripts"
if [[ ! -x "$PY" || ! -x "$PREFLIGHT_PY" || ! -f "$ROOT/requirements-oss.txt" || ! -d "$STATE" ]]; then
  echo "SNS_OSS_LIBRARY_HEALTH=BLOCKED reason=ENV_UNAVAILABLE posts=0" >&2
  exit 78
fi
lock="$STATE/health.lock"
if ! mkdir "$lock" 2>/dev/null; then
  echo "SNS_OSS_LIBRARY_HEALTH=BLOCKED reason=LOCK_BUSY posts=0" >&2
  exit 75
fi
tmp=""
cleanup() {
  if [[ -n "$tmp" && -d "$tmp" && ! -L "$tmp" ]]; then
    case "$tmp" in "$STATE"/probe.*) rm -rf -- "$tmp" ;; esac
  fi
  rmdir "$lock" 2>/dev/null || true
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
tmp="$(mktemp -d "$STATE/probe.XXXXXXXX")"
log="$STATE/last-run-private.log"
: > "$log"
step() {
  local name="$1"
  shift
  if "$@" >> "$log" 2>&1; then
    printf 'SNS_OSS_CHECK=%s status=PASS\n' "$name"
  else
    printf 'SNS_OSS_CHECK=%s status=BLOCKED\n' "$name" >&2
    exit 1
  fi
}
cd "$ROOT"
step yt_dlp "$PY" -m yt_dlp --version
step youtube_providers "$PY" -c 'from youtube_transcript_api import YouTubeTranscriptApi; from youtube_comment_downloader import YoutubeCommentDownloader'
step ffmpeg ffmpeg -version
step ffprobe ffprobe -version
step agent_reach "$STATE/.venv/bin/agent-reach" doctor
step git_clone git clone --quiet --filter=blob:none https://github.com/mvanhorn/last30days-skill.git "$tmp/last30days"
step pinned_revision git -C "$tmp/last30days" checkout --quiet --detach "$PIN"
if [[ "$(git -C "$tmp/last30days" rev-parse HEAD)" != "$PIN" ]]; then
  echo 'SNS_OSS_LIBRARY_HEALTH=BLOCKED reason=REVISION_MISMATCH posts=0' >&2
  exit 78
fi
step last30days_preflight "$PREFLIGHT_PY" "$tmp/last30days/skills/last30days/scripts/last30days.py" --preflight
for test in test_external_library_registry.py test_provider_registry_capabilities.py \
            test_youtube_transcript_provider_contract.py test_threads_comment_parser_post_bound.py; do
  step "$test" "$PY" "$ROOT/scripts/$test"
done
printf 'SNS_OSS_LIBRARY_HEALTH=PASS checks=12 github_actions=false posts=0 writes=0\n'
