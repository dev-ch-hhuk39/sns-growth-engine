#!/usr/bin/env bash
set -euo pipefail

docker stop sns-youtube-pot-provider >/dev/null 2>&1 || true
