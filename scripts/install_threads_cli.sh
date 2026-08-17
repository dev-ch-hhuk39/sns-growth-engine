#!/usr/bin/env bash
set -euo pipefail

VERSION="0.1.1"
INSTALL_DIR="${THREADS_CLI_INSTALL_DIR:-.runtime/bin}"
OS="$(uname -s | tr '[:upper:]' '[:lower:]')"
ARCH="$(uname -m)"
case "$ARCH" in
  x86_64) ARCH="amd64" ;;
  arm64|aarch64) ARCH="arm64" ;;
  *) echo "[BLOCKED] unsupported threads-cli architecture: $ARCH" >&2; exit 2 ;;
esac
case "$OS" in
  linux|darwin) ;;
  *) echo "[BLOCKED] unsupported threads-cli OS: $OS" >&2; exit 2 ;;
esac

ARCHIVE="th_${VERSION}_${OS}_${ARCH}.tar.gz"
case "${OS}_${ARCH}" in
  linux_amd64) EXPECTED="879458f61514bbe6cd7d19043aabdd4d8301d22dbec99118fc70e1dfdde5f403" ;;
  darwin_arm64) EXPECTED="3f59e139746acc63ec5bf46256f8675a7affdd35582b41fa53ed2a2241e12857" ;;
  *) echo "[BLOCKED] no pinned checksum for ${OS}_${ARCH}" >&2; exit 2 ;;
esac

mkdir -p "$INSTALL_DIR"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
curl --fail --location --silent --show-error \
  "https://github.com/tamnd/threads-cli/releases/download/v${VERSION}/${ARCHIVE}" \
  --output "$TMP/$ARCHIVE"
printf '%s  %s\n' "$EXPECTED" "$TMP/$ARCHIVE" | shasum -a 256 --check
tar -xzf "$TMP/$ARCHIVE" -C "$TMP"
install -m 0755 "$TMP/th" "$INSTALL_DIR/th"
"$INSTALL_DIR/th" version
