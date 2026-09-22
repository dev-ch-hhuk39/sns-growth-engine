#!/usr/bin/env bash
set -euo pipefail

DOCKER=(docker)
if ! docker info >/dev/null 2>&1; then
  if command -v sudo >/dev/null 2>&1 && sudo -n docker info >/dev/null 2>&1; then
    DOCKER=(sudo -n docker)
  else
    exit 0
  fi
fi

"${DOCKER[@]}" stop sns-youtube-pot-provider >/dev/null 2>&1 || true
