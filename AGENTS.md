# AGENTS.md — PyPlayVNC LLM Usage Guide

This document is written for AI agents (LLMs) operating this system.
Read it fully before taking any action involving personas, browsers, or the API.

---

## What This System Is

PyPlayVNC is a Dockerized environment that runs persistent Chrome browser profiles
(called **personas**) inside a container with a virtual display (Xvfb) and VNC access.

Each persona is an isolated Chrome session with its own cookies, login state, and
browser history. Personas are used to maintain separate identities for different
accounts (e.g. multiple Gmail logins, SaaS tools, etc.).

The system has two services:

| Service | Host Port | Purpose |
|---|---|---|
| `playwright_vnc` | `5900` | VNC display + Playwright automation runtime |
| `persona_manager` | `8888` | REST API + Web UI to manage personas |

---

## Architecture — Chrome Runs Inside playwright_vnc

Chrome is launched via `docker exec` into the `playwright_vnc` container — **not** inside
the manager container. This is required because Chrome uses X11 MIT-SHM (shared memory)
for rendering, which only works within the same container as Xvfb.

```
persona_manager  →  docker exec playwright_vnc  →  Chrome (inside VNC container)
     (API)                                              ↓
                                                  Xvfb :99 → x11vnc → port 5900
```

Do not attempt to spawn Chrome from outside the `playwright_vnc` container.

---

## Authentication

All API calls require the `X-API-Key` header:

```
X-API-Key: <raw-key>
```

The raw key is stored in the operator's password manager or agent config — NOT in `.env`.
The `.env` file stores only the SHA-256 hash (`API_KEY_HASH`).

If you receive `401` or `403`, the key is missing or wrong. Do not retry blindly — ask
the operator to provide the correct key.

---

## Current Personas

| Name | Account | Purpose | Status |
|---|---|---|---|
| `default` | [REMOVED] | Default persona | logged in |
| `example-persona` | [REMOVED] | Logistics account | logged in |

**One persona per task.** Never use the wrong persona for an account. If you need
`[REMOVED]`, use persona `example-persona`. If you need
`[REMOVED]`, use persona `default`. There is no overlap.

---

## Persona Model

Each persona lives at `profiles/<name>/` on the host, mounted into the container at
`/app/profiles/<name>/`.

A persona has:
- `persona.yml` — metadata (name, description, accounts, notes). Safe to read/write.
- Chrome profile data (`Default/`, `Cookies`, etc.) — session data. Never read or expose.

**Persona states:**

| `has_session` | `browser_running` | Meaning |
|---|---|---|
| false | false | New persona, never logged in |
| false | true | Browser open, login in progress |
| true | false | Logged in, ready for automation |
| true | true | Session active, browser open |

---

## REST API Reference

Base URL: `http://<homelab-ip>:8888`

### List personas
```
GET /api/personas
Headers: X-API-Key: <key>
```

### Get one persona
```
GET /api/personas/{name}
```

### Create persona
```
POST /api/personas
Body: {
  "name": "work-gmail",
  "description": "Work account",
  "accounts": [{"site": "gmail.com", "email": "[REMOVED]"}],
  "notes": ""
}
```
Name: alphanumeric, hyphens, underscores only.

### Update persona metadata
```
PUT /api/personas/{name}
Body: { "description": "...", "accounts": [...], "notes": "..." }
```

### Delete persona
```
DELETE /api/personas/{name}
```
⚠️ Permanently deletes the Chrome profile directory. Cannot be undone.

### Launch browser (for manual login via VNC)
```
POST /api/personas/{name}/launch?url=https://mail.google.com
```
Opens Chromium on the VNC display inside `playwright_vnc`. The human connects to
VNC (port 5900) and logs in manually.

Response: `{"status": "launched", "pid": 123, "url": "...", "persona": "..."}`

### Kill browser
```
POST /api/personas/{name}/kill
```

### Browser status
```
GET /api/personas/{name}/status
```
Returns: `{"persona": "...", "browser_running": bool, "pid": int|null, "has_session": bool}`

---

## Running Automation Scripts

Once a persona has `has_session: true`, use Playwright to automate against it.

### From host:
```bash
docker compose exec -e PERSONA=default playwright-vnc \
    python3 /app/scripts/open_persona.py --url https://mail.google.com --headless
```

### Example — open a specific persona's Gmail headlessly:
```bash
# [REMOVED]
docker compose exec -e PERSONA=default playwright-vnc \
    python3 /app/scripts/open_persona.py --url https://mail.google.com --headless

# [REMOVED]
docker compose exec -e PERSONA=example-persona playwright-vnc \
    python3 /app/scripts/open_persona.py --url https://mail.google.com --headless
```

### Writing your own script:
```python
from playwright.sync_api import sync_playwright
import os

PERSONA = os.getenv("PERSONA", "default")
PROFILE_DIR = f"/app/profiles/{PERSONA}"

with sync_playwright() as p:
    context = p.chromium.launch_persistent_context(
        PROFILE_DIR,
        headless=True,
        args=[
            "--no-sandbox",
            "--disable-blink-features=AutomationControlled",
            "--disable-dev-shm-usage",
            "--disable-gpu",
        ],
    )
    context.add_init_script(
        "Object.defineProperty(navigator, 'webdriver', { get: () => undefined });"
    )
    page = context.new_page()
    page.goto("https://mail.google.com")
    # ... your logic here
    context.close()
```

Place custom scripts in `playwright-scripts/` on the host.
They are not committed to git.

---

## Standard Workflow

### Opening a persona's browser for human interaction (VNC)

1. Launch browser:
```
POST /api/personas/{name}/launch?url=https://mail.google.com
```
2. Tell the human: "Connect to VNC at `<homelab-ip>:5900` to use the browser."
3. When done, kill via API or the human closes Chrome manually.

### First-time login for a new persona

1. Create: `POST /api/personas`
2. Launch: `POST /api/personas/{name}/launch?url=https://mail.google.com`
3. Tell human: "Please connect to VNC at `<homelab-ip>:5900` and log in. Close browser when done."
4. Poll: `GET /api/personas/{name}/status` — wait for `has_session: true`
5. Confirm. Persona is ready.

### Automation (headless, no human needed)

```bash
docker compose exec -e PERSONA={name} playwright-vnc \
    python3 /app/scripts/open_persona.py --url <url> --headless
```

---

## Isolation Rules — No Mixups

- Each persona maps to exactly one set of accounts (see table above)
- Always verify the persona name before launching or running automation
- Before any action, call `GET /api/personas/{name}/status` to check state
- If `browser_running: true`, either reuse the existing session or kill it first — never
  launch a second instance for the same persona
- The `PERSONA` env variable is the only selector — set it explicitly, never rely on defaults
  unless `default` is genuinely what you want

---

## File Locations (inside playwright_vnc container)

| Path | Description |
|---|---|
| `/app/profiles/<name>/` | Persona Chrome profile (host-mounted volume) |
| `/app/profiles/<name>/persona.yml` | Persona metadata |
| `/app/scripts/open_persona.py` | Playwright session helper script |
| `/app/run_browser.sh` | Raw Chromium launcher for manual login |
| `/ms-playwright/chromium-*/chrome-linux64/chrome` | Chromium binary |
| `/tmp/x11vnc.log` | VNC server log |

---

## Error Reference

| HTTP Code | Meaning | Action |
|---|---|---|
| 401 | Missing API key | Add `X-API-Key` header |
| 403 | Wrong API key | Ask operator for correct key |
| 404 | Persona not found | Check name spelling or create it first |
| 409 | Persona already exists | Use PUT to update, or choose a different name |
| 503 | Chromium not found | Docker image issue — rebuild or restart |

---

## What Agents Must NOT Do

- Do not expose or log raw API keys, cookies, session tokens, or profile file contents
- Do not delete a persona without explicit user confirmation
- Do not attempt to automate the Google login flow directly — Google blocks it
- Do not modify `persona.yml` files for personas you didn't create in the current session
  without reading them first
- Do not run multiple browser instances against the same persona simultaneously
- Do not spawn Chrome directly — always use the `/launch` API which handles lock cleanup
  and uses `docker exec` correctly

---

## Quick Reference Card

```bash
KEY="<raw-api-key>"
HOST="localhost"   # or your homelab IP

# List all personas
curl -H "X-API-Key: $KEY" http://$HOST:8888/api/personas

# Check status
curl -H "X-API-Key: $KEY" http://$HOST:8888/api/personas/default/status

# Open browser for human use (VNC:5900)
curl -X POST -H "X-API-Key: $KEY" \
  "http://$HOST:8888/api/personas/default/launch?url=https://mail.google.com"

# Kill browser
curl -X POST -H "X-API-Key: $KEY" http://$HOST:8888/api/personas/default/kill

# Run headless automation
docker compose exec -e PERSONA=default playwright-vnc \
  python3 /app/scripts/open_persona.py --url https://mail.google.com --headless

# Create a new persona
curl -X POST -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
  http://$HOST:8888/api/personas \
  -d '{"name":"work","description":"Work Gmail","accounts":[{"site":"gmail.com","email":"[REMOVED]"}]}'
```
