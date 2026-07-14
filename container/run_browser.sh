#!/usr/bin/env bash
set -Eeuo pipefail

PERSONA="${PERSONA:-default}"
PROFILES_ROOT="${PROFILES_ROOT:-/app/profiles}"
LOCK_ROOT="${LOCK_ROOT:-/tmp/pyplayvnc-locks}"
URL="${1:-https://example.com}"

if [[ ! "$PERSONA" =~ ^[A-Za-z0-9_-]{1,64}$ ]]; then
  echo "ERROR: invalid persona name" >&2
  exit 2
fi
if [[ ! "$URL" =~ ^https?:// ]]; then
  echo "ERROR: only absolute HTTP(S) URLs are allowed" >&2
  exit 2
fi

PROFILE_DIR="${PROFILES_ROOT}/${PERSONA}"
mkdir -p "$PROFILE_DIR" "$LOCK_ROOT"
chmod 0700 "$PROFILE_DIR" "$LOCK_ROOT"

CHROMIUM_BIN="${CHROMIUM_BIN:-}"
if [[ -z "$CHROMIUM_BIN" ]]; then
  CHROMIUM_BIN="$(find /ms-playwright -type f -path '*/chrome-linux64/chrome' -print -quit)"
fi
if [[ -z "$CHROMIUM_BIN" || ! -x "$CHROMIUM_BIN" ]]; then
  echo "ERROR: Chromium executable not found" >&2
  exit 1
fi

exec 9>"${LOCK_ROOT}/${PERSONA}.lock"
if ! flock -n 9; then
  echo "ERROR: persona is already in use" >&2
  exit 3
fi

for lock in SingletonLock SingletonCookie SingletonSocket; do
  rm -f -- "${PROFILE_DIR}/${lock}"
done

exec "$CHROMIUM_BIN" \
  --user-data-dir="$PROFILE_DIR" \
  --password-store=basic \
  --no-first-run \
  --no-default-browser-check \
  --start-maximized \
  "$URL"
