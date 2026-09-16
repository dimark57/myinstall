#!/bin/sh
set -eu

: "${MYINSTALL_URL:?Set a pinned HTTPS myinstall bundle URL}"
: "${MYINSTALL_SHA256:?Set the bundle SHA-256}"

tmp=$(mktemp -d "${TMPDIR:-/tmp}/myinstall.XXXXXX")
trap 'rm -rf "$tmp"' EXIT HUP INT TERM
bundle="$tmp/myinstall"
curl --fail --silent --show-error --location --proto '=https' --tlsv1.2 \
  "$MYINSTALL_URL" -o "$bundle"

if command -v sha256sum >/dev/null 2>&1; then
  actual=$(sha256sum "$bundle" | awk '{print $1}')
else
  actual=$(shasum -a 256 "$bundle" | awk '{print $1}')
fi
[ "$actual" = "$MYINSTALL_SHA256" ] || {
  echo "myinstall checksum mismatch" >&2
  exit 1
}

chmod 700 "$bundle"
exec "$bundle" install --manifest "$(dirname "$0")/manifest.json" --confirm
