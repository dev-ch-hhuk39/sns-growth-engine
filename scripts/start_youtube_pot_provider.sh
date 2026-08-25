#!/usr/bin/env bash
set -euo pipefail

readonly CONTAINER_NAME="sns-youtube-pot-provider"
readonly IMAGE="brainicism/bgutil-ytdlp-pot-provider@sha256:78502f24ce2b716272cf7d6e146f570069b987e9a77a1b346c161ac5bdb028e6"
readonly HEALTH_URL="http://127.0.0.1:4416/ping"

docker run \
  --detach \
  --rm \
  --init \
  --name "$CONTAINER_NAME" \
  --publish 127.0.0.1:4416:4416 \
  "$IMAGE"

for _ in $(seq 1 30); do
  if curl --fail --silent --show-error "$HEALTH_URL" >/dev/null; then
    echo "[OK] bounded YouTube PO Token Provider is ready"
    exit 0
  fi
  sleep 1
done

docker logs "$CONTAINER_NAME" 2>&1 | tail -n 30 || true
echo "[BLOCKED] YouTube PO Token Provider did not become ready" >&2
exit 1
