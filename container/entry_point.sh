#!/usr/bin/env bash
set -Eeuo pipefail

DISPLAY="${DISPLAY:-:99}"
SCREEN_RES="${SCREEN_RES:-1280x1024x24}"
VNC_PASSWORD_FILE="${VNC_PASSWORD_FILE:-/run/secrets/vnc_password}"
export DISPLAY SCREEN_RES

if [[ ! "${API_KEY_HASH:-}" =~ ^[0-9a-fA-F]{64}$ ]]; then
  echo "ERROR: API_KEY_HASH must be a SHA-256 hex digest" >&2
  exit 1
fi
if [[ ! -r "$VNC_PASSWORD_FILE" ]]; then
  echo "ERROR: VNC password secret is missing: $VNC_PASSWORD_FILE" >&2
  exit 1
fi

mkdir -p "$HOME" /tmp/pyplayvnc-locks /tmp/fluxbox /app/profiles /shared
chmod 0700 "$HOME" /tmp/pyplayvnc-locks /app/profiles /shared

vnc_password="$(tr -d '\r\n' < "$VNC_PASSWORD_FILE")"
if (( ${#vnc_password} < 8 )); then
  echo "ERROR: VNC password must contain at least 8 characters" >&2
  exit 1
fi
x11vnc -storepasswd "$vnc_password" /tmp/pyplayvnc-vnc.pass >/dev/null
unset vnc_password
chmod 0600 /tmp/pyplayvnc-vnc.pass

pids=()
# shellcheck disable=SC2329 # Invoked indirectly by the EXIT/TERM/INT trap.
cleanup() {
  trap - EXIT INT TERM
  for pid in "${pids[@]:-}"; do kill "$pid" 2>/dev/null || true; done
  wait 2>/dev/null || true
}
trap cleanup EXIT INT TERM

Xvfb "$DISPLAY" -screen 0 "$SCREEN_RES" -nolisten tcp &
pids+=("$!")
for _ in $(seq 1 40); do
  xdpyinfo -display "$DISPLAY" >/dev/null 2>&1 && break
  sleep 0.25
done
xdpyinfo -display "$DISPLAY" >/dev/null 2>&1 || { echo "ERROR: Xvfb did not start" >&2; exit 1; }

fluxbox -display "$DISPLAY" >/tmp/fluxbox.log 2>&1 &
pids+=("$!")

x11vnc -display "$DISPLAY" -forever -shared -rfbauth /tmp/pyplayvnc-vnc.pass \
  -rfbport 5900 -o /tmp/x11vnc.log &
pids+=("$!")

python3 -m uvicorn manager.main:app --host 0.0.0.0 --port 8080 --no-server-header &
pids+=("$!")

wait -n "${pids[@]}"
echo "ERROR: a required PyPlayVNC service exited" >&2
exit 1
