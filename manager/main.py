"""
manager/main.py — Persona Manager API + UI

Runs alongside the playwright-vnc container (port 8080 internally, 8888 on host).
Shares the same profiles/ volume.

Auth:
  All API and UI routes require:
    Header:  X-API-Key: <raw-key>
  The .env stores only the SHA-256 hash (API_KEY_HASH). The raw key never
  touches disk — store it in your password manager or AI agent config.

REST API:
  GET    /api/personas                  list all personas
  GET    /api/personas/{name}           get one persona + status
  POST   /api/personas                  create persona
  PUT    /api/personas/{name}           update persona metadata
  DELETE /api/personas/{name}           delete persona + all profile data
  POST   /api/personas/{name}/launch    open Chromium for manual login (VNC)
  POST   /api/personas/{name}/kill      kill running browser session
  GET    /api/personas/{name}/status    browser running? session saved?

UI:
  GET /   single-page HTML dashboard
"""

import hashlib
import os
import signal
import subprocess
import shutil
from pathlib import Path
from typing import Optional

import yaml
from fastapi import FastAPI, HTTPException, Depends, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# ─────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────

PROFILES_ROOT = Path(os.getenv("PROFILES_ROOT", "/app/profiles"))
DISPLAY = os.getenv("DISPLAY", ":99")
API_KEY_HASH = os.getenv("API_KEY_HASH", "")

_ms_playwright = Path("/ms-playwright")
CHROMIUM_BIN: Optional[str] = None
if _ms_playwright.exists():
    bins = sorted(_ms_playwright.glob("chromium-*/chrome-linux64/chrome"))
    if bins:
        CHROMIUM_BIN = str(bins[-1])

# Container that runs Xvfb — Chrome must exec here for X11 SHM to work
VNC_CONTAINER: str = os.environ.get("VNC_CONTAINER", "playwright_vnc")

# In-memory PID store  { persona_name: pid }
_running: dict[str, int] = {}

# ─────────────────────────────────────────────
# Auth
# ─────────────────────────────────────────────

def _verify_key(request: Request) -> None:
    """Dependency: validate X-API-Key header against stored hash."""
    if not API_KEY_HASH:
        # Auth not configured — warn but allow (dev mode)
        return
    raw = request.headers.get("X-API-Key", "")
    if not raw:
        raise HTTPException(status_code=401, detail="Missing X-API-Key header")
    provided_hash = hashlib.sha256(raw.encode()).hexdigest()
    if provided_hash != API_KEY_HASH:
        raise HTTPException(status_code=403, detail="Invalid API key")

AuthDep = Depends(_verify_key)

# ─────────────────────────────────────────────
# App
# ─────────────────────────────────────────────

app = FastAPI(
    title="PyPlayVNC Persona Manager",
    description="Manage persistent Chrome profiles / personas for PyPlayVNC",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─────────────────────────────────────────────
# Models
# ─────────────────────────────────────────────

class Account(BaseModel):
    site: str
    email: str

class PersonaMeta(BaseModel):
    name: str
    description: str = ""
    accounts: list[Account] = Field(default_factory=list)
    notes: str = ""

class PersonaStatus(BaseModel):
    name: str
    meta: PersonaMeta
    profile_exists: bool
    has_session: bool
    browser_running: bool
    browser_pid: Optional[int]

class CreatePersona(BaseModel):
    name: str = Field(..., pattern=r"^[a-zA-Z0-9_-]+$")
    description: str = ""
    accounts: list[Account] = Field(default_factory=list)
    notes: str = ""

class UpdatePersona(BaseModel):
    description: Optional[str] = None
    accounts: Optional[list[Account]] = None
    notes: Optional[str] = None

# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────

def _persona_dir(name: str) -> Path:
    return PROFILES_ROOT / name

def _meta_path(name: str) -> Path:
    return _persona_dir(name) / "persona.yml"

def _read_meta(name: str) -> PersonaMeta:
    path = _meta_path(name)
    if not path.exists():
        return PersonaMeta(name=name)
    with open(path) as f:
        data = yaml.safe_load(f) or {}
    return PersonaMeta(
        name=data.get("name", name),
        description=data.get("description", ""),
        accounts=[Account(**a) for a in data.get("accounts", [])],
        notes=data.get("notes", ""),
    )

def _write_meta(meta: PersonaMeta) -> None:
    path = _meta_path(meta.name)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        yaml.dump(
            {
                "name": meta.name,
                "description": meta.description,
                "accounts": [a.model_dump() for a in meta.accounts],
                "notes": meta.notes,
            },
            f,
            default_flow_style=False,
            allow_unicode=True,
        )

def _has_session(name: str) -> bool:
    d = _persona_dir(name)
    return (d / "Default" / "Cookies").exists() or \
           (d / "Default" / "Network" / "Cookies").exists()

def _browser_running(name: str) -> tuple[bool, Optional[int]]:
    pid = _running.get(name)
    if pid is None:
        # Also check if Chrome is running in VNC container even if not tracked
        live_pid = _chrome_pid_in_vnc(name)
        if live_pid:
            _running[name] = live_pid
            return True, live_pid
        return False, None
    # Verify the PID is still alive inside the VNC container
    try:
        result = subprocess.run(
            ["docker", "exec", VNC_CONTAINER, "kill", "-0", str(pid)],
            capture_output=True, timeout=3
        )
        if result.returncode == 0:
            return True, pid
    except Exception:
        pass
    # PID dead — check if a new Chrome spawned
    live_pid = _chrome_pid_in_vnc(name)
    if live_pid:
        _running[name] = live_pid
        return True, live_pid
    _running.pop(name, None)
    return False, None


def _chrome_pid_in_vnc(name: str) -> Optional[int]:
    """Return Chrome PID inside the VNC container for this persona, or None."""
    try:
        result = subprocess.run(
            ["docker", "exec", VNC_CONTAINER, "pgrep", "-n", "-f",
             f"chrome.*{_persona_dir(name)}"],
            capture_output=True, text=True, timeout=5
        )
        s = result.stdout.strip()
        return int(s) if s.isdigit() else None
    except Exception:
        return None

def _list_personas() -> list[str]:
    if not PROFILES_ROOT.exists():
        return []
    return sorted(
        d.name for d in PROFILES_ROOT.iterdir()
        if d.is_dir() and not d.name.startswith(".")
    )

def _build_status(name: str) -> PersonaStatus:
    running, pid = _browser_running(name)
    return PersonaStatus(
        name=name,
        meta=_read_meta(name),
        profile_exists=_persona_dir(name).exists(),
        has_session=_has_session(name),
        browser_running=running,
        browser_pid=pid,
    )

# ─────────────────────────────────────────────
# Routes — UI
# ─────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
def ui():
    """Serve the single-page dashboard. Auth is enforced client-side via stored key."""
    template = Path(__file__).parent / "templates" / "index.html"
    return HTMLResponse(content=template.read_text())

# ─────────────────────────────────────────────
# Routes — Personas
# ─────────────────────────────────────────────

@app.get("/api/personas", response_model=list[PersonaStatus], dependencies=[AuthDep])
def list_personas():
    return [_build_status(n) for n in _list_personas()]


@app.get("/api/personas/{name}", response_model=PersonaStatus, dependencies=[AuthDep])
def get_persona(name: str):
    if not _persona_dir(name).exists():
        raise HTTPException(404, f"Persona '{name}' not found")
    return _build_status(name)


@app.post("/api/personas", response_model=PersonaStatus, status_code=201, dependencies=[AuthDep])
def create_persona(body: CreatePersona):
    if _persona_dir(body.name).exists():
        raise HTTPException(409, f"Persona '{body.name}' already exists")
    meta = PersonaMeta(name=body.name, description=body.description,
                       accounts=body.accounts, notes=body.notes)
    _write_meta(meta)
    return _build_status(body.name)


@app.put("/api/personas/{name}", response_model=PersonaStatus, dependencies=[AuthDep])
def update_persona(name: str, body: UpdatePersona):
    if not _persona_dir(name).exists():
        raise HTTPException(404, f"Persona '{name}' not found")
    meta = _read_meta(name)
    if body.description is not None: meta.description = body.description
    if body.accounts is not None:    meta.accounts = body.accounts
    if body.notes is not None:       meta.notes = body.notes
    _write_meta(meta)
    return _build_status(name)


@app.delete("/api/personas/{name}", status_code=204, dependencies=[AuthDep])
def delete_persona(name: str):
    if not _persona_dir(name).exists():
        raise HTTPException(404, f"Persona '{name}' not found")
    running, pid = _browser_running(name)
    if running and pid:
        try: os.kill(pid, signal.SIGTERM)
        except ProcessLookupError: pass
        _running.pop(name, None)
    shutil.rmtree(_persona_dir(name))


# ─────────────────────────────────────────────
# Routes — Browser Control
# ─────────────────────────────────────────────

def _clear_chrome_locks(profile_dir: Path) -> None:
    """Remove stale Chrome lock files left by crashes or unclean container stops."""
    for f in ["SingletonLock", "SingletonCookie", "SingletonSocket"]:
        (profile_dir / f).unlink(missing_ok=True)
    default = profile_dir / "Default"
    if default.exists():
        for f in ["Login Data-journal", "History-journal", "Favicons-journal",
                  "Web Data-journal", "Shortcuts-journal",
                  "Login Data-shm", "Login Data-wal"]:
            (default / f).unlink(missing_ok=True)
        # Clear segmentation platform DB lock (causes SIGTRAP on relaunch)
        for seg_dir in ["segmentation_platform", "Segmentation Platform"]:
            seg = default / seg_dir
            if seg.exists():
                for lock in seg.rglob("LOCK"):
                    try:
                        lock.unlink()
                    except OSError:
                        pass
        # Clear all remaining LOCK files
        for lock in default.rglob("LOCK"):
            try:
                lock.unlink()
            except OSError:
                pass


@app.post("/api/personas/{name}/launch", dependencies=[AuthDep])
def launch_browser(name: str, url: str = "https://mail.google.com"):
    """
    Launch raw Chromium for this persona. No Playwright — Google cannot detect it.
    The user logs in manually via VNC (localhost:5900).
    """
    if not _persona_dir(name).exists():
        raise HTTPException(404, f"Persona '{name}' not found")

    running, pid = _browser_running(name)
    if running:
        return {"status": "already_running", "pid": pid}

    if not CHROMIUM_BIN or not Path(CHROMIUM_BIN).exists():
        raise HTTPException(503, "Chromium binary not found. Run from inside the playwright-vnc container.")

    # Always clear stale lock files before launching
    _clear_chrome_locks(_persona_dir(name))

    log_path = f"/tmp/chrome_{name}.log"
    log_file = open(log_path, "w")

    # Chrome MUST run inside the playwright-vnc container so it shares
    # the same X11 shared-memory segment as Xvfb. Launching from the
    # manager container causes blank/white screen because MIT-SHM does
    # not work across container boundaries.
    cmd = [
        "docker", "exec", "-d",
        "-e", f"DISPLAY={DISPLAY}",
        VNC_CONTAINER,
        CHROMIUM_BIN,
        "--no-sandbox",
        "--disable-setuid-sandbox",
        "--disable-gpu-sandbox",
        f"--user-data-dir={_persona_dir(name)}",
        "--disable-blink-features=AutomationControlled",
        "--disable-dev-shm-usage",
        "--disable-gpu",
        "--disable-software-rasterizer",
        "--disable-gpu-compositing",
        "--in-process-gpu",
        "--password-store=basic",
        "--no-first-run",
        "--no-default-browser-check",
        "--start-maximized",
        url,
    ]

    proc = subprocess.Popen(
        cmd,
        stdout=log_file,
        stderr=log_file,
    )
    proc.wait()  # docker exec -d returns immediately with the container's PID in stdout

    # Find the PID of the newly launched Chrome inside the VNC container
    import time
    time.sleep(2)
    try:
        result = subprocess.run(
            ["docker", "exec", VNC_CONTAINER, "pgrep", "-n", "-f", f"chrome.*{_persona_dir(name)}"],
            capture_output=True, text=True, timeout=5
        )
        pid = int(result.stdout.strip()) if result.stdout.strip().isdigit() else 0
    except Exception:
        pid = 0

    _running[name] = pid
    return {"status": "launched", "pid": pid, "url": url, "persona": name}


@app.post("/api/personas/{name}/kill", dependencies=[AuthDep])
def kill_browser(name: str):
    running, pid = _browser_running(name)
    if not running or not pid:
        return {"status": "not_running"}
    try:
        subprocess.run(
            ["docker", "exec", VNC_CONTAINER, "kill", str(pid)],
            capture_output=True, timeout=5
        )
    except Exception:
        pass
    _running.pop(name, None)
    return {"status": "killed", "pid": pid}


@app.get("/api/personas/{name}/status", dependencies=[AuthDep])
def browser_status(name: str):
    running, pid = _browser_running(name)
    return {
        "persona": name,
        "browser_running": running,
        "pid": pid,
        "has_session": _has_session(name),
    }
