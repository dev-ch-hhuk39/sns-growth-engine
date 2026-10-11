#!/usr/bin/env bash
# SNS deployment gate, delegated to the shared VPS administrator's policy.
# There is deliberately no df/free fallback: an unavailable gate is a block.
set -euo pipefail

minimum_free_gib=8
if [[ $# -gt 0 ]]; then
  if [[ $# -ne 2 || "$1" != "--min-free-gib" ]]; then
    echo '[BLOCKED] usage: check_chadult_vps_deploy_preflight.sh [--min-free-gib 8..1024]' >&2
    exit 64
  fi
  minimum_free_gib="$2"
fi
if [[ ! "$minimum_free_gib" =~ ^[0-9]+$ ]] || (( ${#minimum_free_gib} > 4 )); then
  echo '[BLOCKED] invalid deployment free-space requirement' >&2
  exit 64
fi
if (( minimum_free_gib < 8 || minimum_free_gib > 1024 )); then
  echo '[BLOCKED] deployment requires at least 8 GiB and at most 1024 GiB' >&2
  exit 64
fi
if ! command -v sudo >/dev/null 2>&1; then
  echo '[BLOCKED] privileged shared VPS resource gate unavailable' >&2
  exit 78
fi
# The root-owned executable is the cross-tool resource policy source of truth.
# A narrowly scoped sudoers allowance for snsrunner must be deployed by VPS Ops.
if ! sudo -n /usr/local/sbin/chadult-vps-resource-check --preflight "$minimum_free_gib"; then
  echo '[BLOCKED] shared VPS resource preflight denied or unavailable' >&2
  exit 78
fi
echo '[OK] shared VPS resource preflight passed'
