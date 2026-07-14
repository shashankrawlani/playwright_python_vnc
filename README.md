# PyPlayVNC

Dockerized persistent Chrome browser automation with multi-persona profile management,
VNC access, and a REST API + web UI for control.

**Stack:** Python 3.12 · Playwright 1.61.0 · Chromium 149 · Xvfb · x11vnc · Fluxbox · FastAPI

---

## What It Does

- Runs persistent Chrome sessions called **personas** inside Docker
- Each persona has its own isolated Chrome profile — separate cookies, logins, history
- VNC access (port 5900) lets you see and interact with the browser visually
- Persona Manager (port 8888) lets you create, launch, and control personas via web UI or REST API
- Playwright automation scripts reuse saved login sessions without triggering bot detection
- Profiles are stored on the host — portable, easy to back up and migrate

---

## Architecture

```
┌─────────────────────────────────────────────────┐
│  Host machine                                   │
│                                                 │
│  ./profiles/          ← Chrome profiles (host   │
│    default/           ←   volume, persisted)    │
│    example-persona/                            │
│                                                 │
│  ┌──────────────────────────────────────────┐   │
│  │  playwright_vnc container                │   │
│  │                                          │   │
│  │  Xvfb :99  ←  x11vnc → port 5900 (VNC)  │   │
│  │  Fluxbox                                 │   │
│  │  Chrome (launched via docker exec)       │   │
│  │                                          │   │
│  │  port 8888 ──────────────────────────┐   │   │
│  └──────────────────────────────────────┼───┘   │
│                                         │       │
│  ┌──────────────────────────────────────┼───┐   │
│  │  persona_manager container           │   │   │
│  │  (shares network namespace)          │   │   │
│  │                                      │   │   │
│  │  FastAPI on :8080 ───────────────────┘   │   │
│  │  Uses docker exec to launch Chrome       │   │
│  │  inside playwright_vnc (MIT-SHM fix)     │   │
│  └──────────────────────────────────────────┘   │
└─────────────────────────────────────────────────┘
```

**Why `docker exec`?** Chrome uses X11 MIT-SHM (shared memory) for rendering. If Chrome
runs in a different container than Xvfb, the shared memory segment can't be accessed and
the screen stays blank. Chrome must run inside `playwright_vnc` to share its memory space.

---

## Quick Start

```bash
git clone https://github.com/shashankrawlani/playwright_python_vnc
cd playwright_python_vnc
cp .env.example .env
# Edit .env — generate and add API_KEY_HASH (see Auth section)
docker compose up -d
```

**Access:**
- Persona Manager UI: `http://localhost:8888`
- VNC (live browser): `localhost:5900` — connect with any VNC viewer (no password)
- API docs (Swagger): `http://localhost:8888/docs`

---

## Auth Setup

The manager API requires an API key. Only the SHA-256 hash is stored in `.env`.

```bash
python3 -c "
import secrets, hashlib
k = secrets.token_urlsafe(32)
print('RAW  (save to password manager):', k)
print('HASH (put in .env):', hashlib.sha256(k.encode()).hexdigest())
"
```

Add to `.env`:
```
API_KEY_HASH=<the-hash-output>
```

Store the **raw key** in your password manager. Never put it in `.env` or commit it.

---

## Current Personas

| Name | Purpose |
|---|---|
| `default` | Primary persona — see `profiles/default/persona.yml` |
| `example-persona` | Logistics account — see `profiles/example-persona/persona.yml` |

---

## Persona Workflow

### 1 — Create a persona

Via UI: `http://localhost:8888` → **+ New Persona**

Via API:
```bash
curl -X POST -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
  http://localhost:8888/api/personas \
  -d '{"name":"work","description":"Work Gmail","accounts":[{"site":"gmail.com","email":"[REMOVED]"}]}'
```

### 2 — Login manually via VNC (once per persona)

```bash
curl -X POST -H "X-API-Key: $KEY" \
  "http://localhost:8888/api/personas/work/launch?url=https://mail.google.com"
```

Connect to `localhost:5900` in your VNC viewer → complete login → close the browser.
The session is saved to `profiles/work/`. You never need to repeat this.

### 3 — Automate with Playwright

```bash
# Headless (no visible browser)
docker compose exec -e PERSONA=work playwright-vnc \
    python3 /app/scripts/open_persona.py --url https://mail.google.com --headless

# Visible in VNC
docker compose exec -e PERSONA=work playwright-vnc \
    python3 /app/scripts/open_persona.py --url https://mail.google.com
```

---

## Persona Isolation

Each persona is completely isolated:

- Separate Chrome profile directory — no shared cookies, storage, or history
- The `PERSONA` environment variable selects which profile is used
- Scripts running with `PERSONA=work` never touch `PERSONA=default`
- Two personas can NOT run simultaneously against the same profile directory

**Never:**
- Open the same persona in two browser instances at the same time
- Expose or log the contents of `profiles/<name>/Default/Cookies`

---

## REST API

All endpoints require `X-API-Key: <raw-key>` header.
Full interactive docs: `http://localhost:8888/docs`

| Method | Path | Description |
|---|---|---|
| GET | `/api/personas` | List all personas + status |
| GET | `/api/personas/{name}` | Get one persona |
| POST | `/api/personas` | Create persona |
| PUT | `/api/personas/{name}` | Update metadata |
| DELETE | `/api/personas/{name}` | Delete persona + all data |
| POST | `/api/personas/{name}/launch` | Open browser for manual login |
| POST | `/api/personas/{name}/kill` | Kill running browser |
| GET | `/api/personas/{name}/status` | Running? Session saved? |

---

## Writing Automation Scripts

Place scripts in `playwright-scripts/` (not committed):

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
    # your automation here
    context.close()
```

Run it:
```bash
docker compose exec -e PERSONA=work playwright-vnc \
    python3 /app/playwright-scripts/your_script.py
```

---

## Project Structure

```
playwright_python_vnc/
│
├── docker-compose.yml          ← start/stop everything
├── Dockerfile                  ← VNC+Playwright image
├── .env                        ← local secrets (not committed)
├── .env.example                ← template — copy to .env
│
├── container/                  ← baked into the Docker image
│   ├── entry_point.sh          (starts Xvfb, VNC, Fluxbox)
│   ├── run_browser.sh          (opens Chromium for manual login)
│   └── scripts/
│       └── open_persona.py     (Playwright session reuse helper)
│
├── manager/                    ← Persona Manager (FastAPI, live-mounted)
│   ├── main.py
│   ├── requirements.txt
│   └── templates/index.html
│
├── profiles/                   ← Chrome profiles (host volume, persisted)
│   ├── default/
│   │   ├── persona.yml         ← metadata (committed)
│   │   └── Default/            ← Chrome session data (committed for migration)
│   └── example-persona/
│       ├── persona.yml
│       └── Default/
│
├── playwright-scripts/         ← your automation scripts (not committed)
├── shared/                     ← file exchange host ↔ container
├── AGENTS.md                   ← LLM/AI agent usage guide
└── docs/
    └── MIGRATION.md            ← moving to another machine
```

---

## Backup & Restore

```bash
# Backup everything (profiles + config)
tar -czf pyplayvnc_backup_$(date +%Y%m%d).tar.gz \
  profiles/ manager/ container/ docker-compose.yml .env .env.example \
  Dockerfile AGENTS.md README.md

# Restore
tar -xzf pyplayvnc_backup_20260714.tar.gz
docker compose up -d
```

For full migration steps see **[docs/MIGRATION.md](./docs/MIGRATION.md)**.

---

## Services

| Service | Port | Description |
|---|---|---|
| `playwright-vnc` | 5900 | Xvfb + VNC + Chromium + Playwright runtime |
| `manager` | 8888 | Persona Manager web UI + REST API |

```bash
docker compose up -d            # start everything
docker compose down             # stop (profiles preserved on host)
docker compose logs -f manager  # watch manager logs
docker compose restart manager  # restart after config change
```

---

## Rebuild the Image

Only needed when `Dockerfile` or `container/` files change. Profile data is never in the image.

```bash
docker build -t shashankrawlani/playwright_python_vnc:latest .
docker compose up -d --force-recreate
```

---

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `DISPLAY` | `:99` | Xvfb display number |
| `SCREEN_RES` | `1280x1024x24` | VNC screen resolution |
| `PROFILES_ROOT` | `/app/profiles` | Multi-persona root directory |
| `PERSONA` | `default` | Active persona for automation scripts |
| `API_KEY_HASH` | — | SHA-256 hash of manager API key |
| `VNC_CONTAINER` | `playwright_vnc` | Container name where Chrome runs |

---

## For AI Agents

See **[AGENTS.md](./AGENTS.md)** — full API reference, isolation rules, docker exec usage,
and rules for LLMs operating this system.
