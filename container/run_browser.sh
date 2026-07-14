#!/bin/bash
# ─────────────────────────────────────────────────────────────
# run_browser.sh — Open Chromium for a persona (manual login)
#
# Usage (from host):
#   docker compose exec playwright-vnc /app/run_browser.sh
#   docker compose exec -e PERSONA=persona1 playwright-vnc /app/run_browser.sh
#
# Or directly inside container shell:
#   PERSONA=persona1 /app/run_browser.sh
#   /app/run_browser.sh gmail.com          # opens a URL directly
#
# The browser is NOT launched via Playwright, so Google/other sites
# cannot detect automation. Login manually via VNC, then close the
# browser — your session is saved to the profile directory.
# ─────────────────────────────────────────────────────────────
set -euo pipefail

PERSONA="${PERSONA:-default}"
PROFILE_DIR="/app/profiles/${PERSONA}"
CHROMIUM_BIN="$(find /ms-playwright -name 'chrome' | grep -v firefox | head -1)"
URL="${1:-about:newtab}"

# ── Validate ──────────────────────────────────────────────────
if [ -z "$CHROMIUM_BIN" ]; then
    echo "❌ Chromium binary not found in /ms-playwright"
    exit 1
fi

if [ ! -d "$PROFILE_DIR" ]; then
    echo "⚠️  Profile directory not found: $PROFILE_DIR"
    echo "   Creating it now..."
    mkdir -p "$PROFILE_DIR"
fi

# ── Clean up stale Chrome lock files ─────────────────────────
# Chrome leaves these behind after crashes or unclean container stops.
# Safe to remove — Chrome recreates them on startup.
echo "🧹 Clearing any stale Chrome lock files..."
rm -f \
    "$PROFILE_DIR/SingletonLock" \
    "$PROFILE_DIR/SingletonCookie" \
    "$PROFILE_DIR/SingletonSocket"
# Also clear database journal/lock files if present
DEFAULT_DIR="$PROFILE_DIR/Default"
if [ -d "$DEFAULT_DIR" ]; then
    rm -f "$DEFAULT_DIR/Login Data-journal" \
          "$DEFAULT_DIR/History-journal" \
          "$DEFAULT_DIR/Favicons-journal" \
          "$DEFAULT_DIR/Web Data-journal" \
          "$DEFAULT_DIR/Shortcuts-journal" \
          "$DEFAULT_DIR/Login Data-shm" \
          "$DEFAULT_DIR/Login Data-wal"
    find "$DEFAULT_DIR/Local Storage" -name "LOCK" -delete 2>/dev/null || true
    find "$DEFAULT_DIR/IndexedDB"     -name "LOCK" -delete 2>/dev/null || true
fi

# ── Launch ────────────────────────────────────────────────────
echo ""
echo "🧑 Persona     : $PERSONA"
echo "📂 Profile dir : $PROFILE_DIR"
echo "🌐 Opening URL : $URL"
echo "🖥️  Connect VNC  : localhost:5900"
echo ""
echo "👉 Login manually in the browser window, then close it."
echo "   Your session will be saved and reused by Playwright scripts."
echo ""

exec "$CHROMIUM_BIN" \
    --no-sandbox \
    --disable-setuid-sandbox \
    --disable-gpu-sandbox \
    --user-data-dir="$PROFILE_DIR" \
    --disable-blink-features=AutomationControlled \
    --disable-infobars \
    --disable-dev-shm-usage \
    --disable-gpu \
    --disable-software-rasterizer \
    --disable-gpu-compositing \
    --in-process-gpu \
    --password-store=basic \
    --no-first-run \
    --no-default-browser-check \
    --start-maximized \
    "$URL"
