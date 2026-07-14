#!/bin/bash
set -euo pipefail
# ┌────────────────────────────────────────────────────────┐
# │ PyPlayVNC - GhostBrowser for entrypoint.sh 🚀         │
# └────────────────────────────────────────────────────────┘

cat <<'EOF'
 ____        ____  _           __     ___   _  ____              
|  _ \ _   _|  _ \| | __ _ _   \ \   / / \ | |/ ___|             
| |_) | | | | |_) | |/ _` | | | \ \ / /|  \| | |      _____      
|  __/| |_| |  __/| | (_| | |_| |\ V / | |\  | |___  |_____|     
|_|    \__, |_|   |_|\__,_|\__, | \_/  |_| \_|\____|             
  ____ |___/           _   |___/                                 
 / ___| |__   ___  ___| |_| __ ) _ __ _____      _____  ___ _ __ 
| |  _| '_ \ / _ \/ __| __|  _ \| '__/ _ \ \ /\ / / __|/ _ \ '__|
| |_| | | | | (_) \__ \ |_| |_) | | | (_) \ V  V /\__ \  __/ |   
 \____|_| |_|\___/|___/\__|____/|_|  \___/ \_/\_/ |___/\___|_|   

🐍 Python + 🎭 Playwright + 🖥️ VNC + 📦 Xvfb + 🎛️ Fluxbox
Dockerhub - shashankrawlani/playwright_python_vnc
EOF

# ─────────────────────────────────────────────
# 💡 ENV & SETUP HELPERS
# ─────────────────────────────────────────────
# Load from .env if it exists
if [ -f "/app/.env" ]; then
    echo "📥 Loading environment from .env"
    set +u  # allow unbound vars while sourcing .env
    set -o allexport
    # shellcheck source=/dev/null
    source /app/.env
    set +o allexport
    set -u
fi

export DISPLAY="${DISPLAY:-:99}"
export USER_DATA_DIR="${USER_DATA_DIR:-/app/user_data}"
export SCREEN_RES="${SCREEN_RES:-1280x1024x24}"

# PID tracking
XVFB_PID=""
X11VNC_PID=""
FLUXBOX_PID=""

setup_dirs() {
    mkdir -p "$USER_DATA_DIR" /shared
    chmod -R 777 "$USER_DATA_DIR" /shared
}

check_env() {
    if [ ! -d "/app" ]; then
        echo "❌ Must run inside container."
        exit 1
    fi
    echo "✅ Working in /app"
    echo "✅ DISPLAY=$DISPLAY"
    echo "✅ USER_DATA_DIR=$USER_DATA_DIR"
}

# ─────────────────────────────────────────────
# 🎛 STARTERS
# ─────────────────────────────────────────────

start_xvfb() {
    echo "📦 Starting Xvfb..."
    Xvfb "$DISPLAY" -screen 0 "$SCREEN_RES" &
    XVFB_PID=$!
    # Wait until the display is actually available
    for i in $(seq 1 10); do
        xdpyinfo -display "$DISPLAY" >/dev/null 2>&1 && break
        sleep 0.5
    done
    echo "✅ Xvfb ready (PID $XVFB_PID)"
}

start_vnc() {
    echo "🖥️  Starting x11vnc..."
    x11vnc -display "$DISPLAY" -forever -nopw -bg -o /tmp/x11vnc.log
    X11VNC_PID=$(pgrep -n x11vnc || true)
    echo "✅ x11vnc ready (PID $X11VNC_PID)"
}

start_fluxbox() {
    echo "🎛️  Starting Fluxbox..."
    DISPLAY="$DISPLAY" fluxbox &
    FLUXBOX_PID=$!
    sleep 1
    echo "✅ Fluxbox ready (PID $FLUXBOX_PID)"
}

start_all() {
    setup_dirs
    start_xvfb
    start_vnc
    start_fluxbox
}

# ─────────────────────────────────────────────
# 🔍 ENVIRONMENT CHECKS
# ─────────────────────────────────────────────

env_check() {
    echo ""
    echo "🐍 Python version:" && python --version
    echo ""
    echo "🎭 Playwright via Python:"
    python -c "import importlib.metadata as m; print('✅ Python Playwright version:', m.version('playwright'))" 2>/dev/null \
        || echo "❌ playwright package not found"
    echo ""
    echo "🎭 Playwright CLI:"
    playwright --version 2>/dev/null || echo "❌ CLI not found"
    echo ""
    echo "✅ Environment check complete!"
}

# ─────────────────────────────────────────────
# 🧹 CLEANUP
# ─────────────────────────────────────────────

cleanup_services() {
    echo "🧹 Stopping services..."
    # Only kill PIDs that were actually started
    [ -n "$FLUXBOX_PID" ] && kill "$FLUXBOX_PID" 2>/dev/null || true
    [ -n "$X11VNC_PID" ]  && kill "$X11VNC_PID"  2>/dev/null || true
    [ -n "$XVFB_PID" ]    && kill "$XVFB_PID"    2>/dev/null || true
}

trap cleanup_services INT TERM EXIT

# ─────────────────────────────────────────────
# 🚀 BOOTSTRAP
# ─────────────────────────────────────────────

check_env
start_all
env_check

# Stay alive — wait on Xvfb so container exits cleanly if it dies
wait "$XVFB_PID"
