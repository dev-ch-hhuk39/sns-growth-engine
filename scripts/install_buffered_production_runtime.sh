#!/usr/bin/env bash
# Install an immutable VPS release.  This script never copies an arbitrary
# runner worktree into the live path: the caller must name a commit-shaped
# revision and explicitly confirm the installation.
set -euo pipefail

RUNTIME_ROOT="${BUFFERED_RUNTIME_ROOT:-/opt/sns-growth-engine}"
SOURCE_ROOT=""
REVISION=""
APPLY="false"
CONFIRMED="false"

usage() {
  echo "usage: $0 --source-root <checkout> --revision <git-sha> [--dry-run | --apply --confirm-install]" >&2
}
while [[ $# -gt 0 ]]; do
  case "$1" in
    --source-root) SOURCE_ROOT="${2:-}"; shift 2 ;;
    --revision) REVISION="${2:-}"; shift 2 ;;
    --dry-run) shift ;;
    --apply) APPLY="true"; shift ;;
    --confirm-install) CONFIRMED="true"; shift ;;
    *) usage; exit 64 ;;
  esac
done

[[ -n "$SOURCE_ROOT" && -f "$SOURCE_ROOT/scripts/reconcile_due_production_slots.py" ]] || { echo "[BLOCKED] source checkout is incomplete" >&2; exit 64; }
[[ "$REVISION" =~ ^[0-9a-f]{7,64}$ ]] || { echo "[BLOCKED] revision must be a commit SHA" >&2; exit 64; }
if [[ "$APPLY" != "true" ]]; then
  echo "[PLAN_ONLY] release=${RUNTIME_ROOT}/releases/${REVISION}"
  exit 0
fi
[[ "$CONFIRMED" == "true" ]] || { echo "[BLOCKED] explicit --confirm-install is required" >&2; exit 64; }

mkdir -p "$RUNTIME_ROOT/releases" "$RUNTIME_ROOT/shared/locks" "$RUNTIME_ROOT/shared/threads_tokens"
target="$RUNTIME_ROOT/releases/$REVISION"
if [[ ! -d "$target" ]]; then
  stage="$(mktemp -d "$RUNTIME_ROOT/releases/.stage-${REVISION}.XXXXXX")"
  rsync -a --delete --exclude .git --exclude .runtime --exclude data --exclude output --exclude .ai-tmp "$SOURCE_ROOT/" "$stage/"
  printf '%s\n' "$REVISION" > "$stage/.production-release"
  python3 -m venv "$stage/.venv"
  "$stage/.venv/bin/pip" install --quiet -r "$stage/requirements.txt"
  mv "$stage" "$target"
fi
ln -sfn "$target" "$RUNTIME_ROOT/current"
echo "[OK] production runtime release installed: $REVISION"
