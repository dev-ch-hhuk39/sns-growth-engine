#!/usr/bin/env bash
set -euo pipefail

readonly CONTAINER_NAME="sns-youtube-pot-provider"
readonly PROVIDER_VERSION="2.0.0"
readonly IMAGE="brainicism/bgutil-ytdlp-pot-provider@sha256:ed86b6fdd5e430ddd7c8ce1adb55e1ab54db7c7dbc1bcbf3a82454a85b971164"
readonly HEALTH_URL="http://127.0.0.1:4416/ping"

installed_version="$(python3 -c 'import importlib.metadata; print(importlib.metadata.version("bgutil-ytdlp-pot-provider"))')"
if [[ "$installed_version" != "$PROVIDER_VERSION" ]]; then
  echo "[BLOCKED] YouTube PO Token Provider plugin/server version mismatch" >&2
  exit 1
fi

docker run \
  --detach \
  --rm \
  --init \
  --name "$CONTAINER_NAME" \
  --publish 127.0.0.1:4416:4416 \
  "$IMAGE"

for _ in $(seq 1 30); do
  if curl --fail --silent --show-error "$HEALTH_URL" >/dev/null; then
    echo "[OK] bounded YouTube PO Token Provider ${PROVIDER_VERSION} is ready"
    exit 0
  fi
  sleep 1
done

docker logs "$CONTAINER_NAME" 2>&1 | tail -n 30 || true
echo "[BLOCKED] YouTube PO Token Provider did not become ready" >&2
exit 1
