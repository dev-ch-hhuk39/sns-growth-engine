#!/bin/bash
# Live public reference lookups, private previews only. No hosted Actions.
set -euo pipefail
umask 077
ROOT=/Users/hayatoa/Projects/sns-growth-engine-bank-acceptance-20261024
STATE="$HOME/.cache/chadult-sns-source-research"
PATH=/Library/Frameworks/Python.framework/Versions/3.13/bin:/opt/homebrew/bin:/usr/bin:/bin
export PATH
unset OPENAI_API_KEY ANTHROPIC_API_KEY GEMINI_API_KEY GOOGLE_API_KEY GITHUB_TOKEN GH_TOKEN
unset SA_JSON_BASE64 GCP_SA_JSON_BASE64 SPREADSHEET_ID SNS_MASTER_SHEET_ID
unset THREADS_ACCESS_TOKEN_NIGHT_SCOUT THREADS_ACCESS_TOKEN_LIVER_MANAGER THREADS_ACCESS_TOKEN_BEAUTY_ACCOUNT
export PUBLISH_ENABLED=false ALLOW_REAL_THREADS_POST=false ALLOW_REAL_X_POST=false
export ALLOW_VIDEO_DOWNLOAD=false ALLOW_VIDEO_CUT=false ALLOW_CLOUDINARY_UPLOAD=false
export ALLOW_MEDIA_POSTS=false
if [[ ! -d "$STATE" || -L "$STATE" || ! -f "$ROOT/config/research_topics.json" ]];then
  echo 'SNS_LOCAL_SOURCE_RESEARCH=BLOCKED reason=STATE_OR_TOPICS_UNAVAILABLE' >&2
  exit 78
fi
mkdir -p "$STATE/previews"
chmod 700 "$STATE/previews"
lock="$STATE/source-research.lock"
if ! mkdir "$lock" 2>/dev/null;then
  echo 'SNS_LOCAL_SOURCE_RESEARCH=BLOCKED reason=EXCLUSIVE_LOCK_BUSY' >&2
  exit 75
fi
trap 'rmdir "$lock" 2>/dev/null || true' EXIT
cd "$ROOT"
/Library/Frameworks/Python.framework/Versions/3.13/bin/python3 \
    scripts/sns_local_source_research_preview.py
