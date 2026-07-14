"""Secure Persona Manager for PyPlayVNC.

The manager, Chromium, Xvfb, and VNC run in one container. This avoids mounting the
host Docker socket. Runtime profiles are local secrets and must never be committed.
"""

from __future__ import annotations

import fcntl
import hashlib
import hmac
import os
import re
import shutil
import signal
import subprocess
import threading
import time
from collections import defaultdict, deque
from pathlib import Path
from typing import BinaryIO
from urllib.parse import urlparse

import yaml
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel, Field

PROFILES_ROOT = Path(os.getenv("PROFILES_ROOT", "/app/profiles")).resolve()
DISPLAY = os.getenv("DISPLAY", ":99")
API_KEY_HASH = os.getenv("API_KEY_HASH", "")
PERSONA_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
LOCK_ROOT = Path(os.getenv("LOCK_ROOT", "/tmp/pyplayvnc-locks"))

if not re.fullmatch(r"[0-9a-fA-F]{64}", API_KEY_HASH):
    raise RuntimeError("API_KEY_HASH must be configured as a 64-character SHA-256 hex digest")


def _find_chromium() -> str:
    configured = os.getenv("CHROMIUM_BIN")
    if configured and Path(configured).is_file():
        return configured
    candidates = list(Path("/ms-playwright").glob("chromium-*/chrome-linux64/chrome"))
    if not candidates:
        raise RuntimeError("Playwright Chromium executable not found")
    return str(max(candidates, key=lambda p: p.stat().st_mtime))


CHROMIUM_BIN = _find_chromium()
_OPERATIONS_LOCK = threading.RLock()
_PROCESSES: dict[str, subprocess.Popen[bytes]] = {}
_PROFILE_LOCKS: dict[str, BinaryIO] = {}
_AUTH_FAILURES: dict[str, deque[float]] = defaultdict(deque)
_AUTH_LOCK = threading.Lock()
AUTH_WINDOW_SECONDS = 60
AUTH_MAX_FAILURES = 10


class Account(BaseModel):
    site: str = Field(min_length=1, max_length=255)
    email: str = Field(default="", max_length=320)


class PersonaMeta(BaseModel):
    name: str
    description: str = Field(default="", max_length=1000)
    accounts: list[Account] = Field(default_factory=list, max_length=50)
    notes: str = Field(default="", max_length=4000)


class PersonaStatus(BaseModel):
    name: str
    meta: PersonaMeta
    profile_exists: bool
    has_session: bool
    browser_running: bool
    browser_pid: int | None


class CreatePersona(BaseModel):
    name: str = Field(..., pattern=r"^[A-Za-z0-9_-]{1,64}$")
    description: str = Field(default="", max_length=1000)
    accounts: list[Account] = Field(default_factory=list, max_length=50)
    notes: str = Field(default="", max_length=4000)


class UpdatePersona(BaseModel):
    description: str | None = Field(default=None, max_length=1000)
    accounts: list[Account] | None = Field(default=None, max_length=50)
    notes: str | None = Field(default=None, max_length=4000)


def _verify_key(request: Request) -> None:
    client = request.client.host if request.client else "unknown"
    now = time.monotonic()
    with _AUTH_LOCK:
        failures = _AUTH_FAILURES[client]
        while failures and now - failures[0] > AUTH_WINDOW_SECONDS:
            failures.popleft()
        if len(failures) >= AUTH_MAX_FAILURES:
            raise HTTPException(status_code=429, detail="Too many failed authentication attempts")
    raw = request.headers.get("X-API-Key", "")
    if not raw:
        with _AUTH_LOCK:
            _AUTH_FAILURES[client].append(now)
        raise HTTPException(status_code=401, detail="Missing API key")
    supplied = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    if not hmac.compare_digest(supplied.lower(), API_KEY_HASH.lower()):
        with _AUTH_LOCK:
            _AUTH_FAILURES[client].append(now)
        raise HTTPException(status_code=403, detail="Invalid API key")
    with _AUTH_LOCK:
        _AUTH_FAILURES.pop(client, None)


Auth = Depends(_verify_key)
app = FastAPI(
    title="PyPlayVNC Persona Manager",
    version="2.0.0",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response: Response = await call_next(request)
    response.headers["Cache-Control"] = "no-store"
    response.headers["Content-Security-Policy"] = (
        "default-src 'none'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
        "connect-src 'self'; img-src 'self' data:; base-uri 'none'; "
        "form-action 'self'; frame-ancestors 'none'"
    )
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    return response


def _validate_name(name: str) -> str:
    if not PERSONA_RE.fullmatch(name):
        raise HTTPException(status_code=422, detail="Invalid persona name")
    return name


def _persona_dir(name: str) -> Path:
    safe_name = _validate_name(name)
    candidate = (PROFILES_ROOT / safe_name).resolve()
    if candidate.parent != PROFILES_ROOT:
        raise HTTPException(status_code=422, detail="Invalid persona path")
    return candidate


def _meta_path(name: str) -> Path:
    return _persona_dir(name) / "persona.yml"


def _read_meta(name: str) -> PersonaMeta:
    safe_name = _validate_name(name)
    path = _meta_path(safe_name)
    if not path.exists():
        return PersonaMeta(name=safe_name)
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        return PersonaMeta(
            name=safe_name,
            description=data.get("description", ""),
            accounts=[Account(**a) for a in data.get("accounts", [])],
            notes=data.get("notes", ""),
        )
    except (OSError, TypeError, ValueError, yaml.YAMLError) as exc:
        raise HTTPException(status_code=500, detail=f"Invalid persona metadata for {safe_name}") from exc


def _write_meta(name: str, meta: PersonaMeta) -> None:
    path = _meta_path(name)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    payload = {
        "name": name,
        "description": meta.description,
        "accounts": [a.model_dump() for a in meta.accounts],
        "notes": meta.notes,
    }
    temp = path.with_suffix(".yml.tmp")
    temp.write_text(yaml.safe_dump(payload, sort_keys=False, allow_unicode=True), encoding="utf-8")
    temp.chmod(0o600)
    os.replace(temp, path)


def _list_personas() -> list[str]:
    if not PROFILES_ROOT.exists():
        return []
    return sorted(
        item.name
        for item in PROFILES_ROOT.iterdir()
        if item.is_dir() and PERSONA_RE.fullmatch(item.name) and (item / "persona.yml").is_file()
    )


def _has_session(name: str) -> bool:
    directory = _persona_dir(name)
    return any(
        path.exists()
        for path in (
            directory / "Default" / "Cookies",
            directory / "Default" / "Network" / "Cookies",
        )
    )


def _profile_arg(name: str) -> str:
    return f"--user-data-dir={_persona_dir(name)}"


def _matching_pids(name: str) -> list[int]:
    expected = _profile_arg(name)
    matches: list[int] = []
    for proc in Path("/proc").iterdir():
        if not proc.name.isdigit():
            continue
        try:
            args = (proc / "cmdline").read_bytes().split(b"\0")
            decoded = [arg.decode("utf-8", "replace") for arg in args if arg]
        except (FileNotFoundError, PermissionError, ProcessLookupError, OSError):
            continue
        if expected in decoded and decoded and Path(decoded[0]).name in {"chrome", "chromium", "chromium-browser"}:
            matches.append(int(proc.name))
    return sorted(matches)


def _release_profile_lock(name: str) -> None:
    handle = _PROFILE_LOCKS.pop(name, None)
    if handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_UN)
        finally:
            handle.close()


def _acquire_profile_lock(name: str) -> None:
    if name in _PROFILE_LOCKS:
        return
    LOCK_ROOT.mkdir(parents=True, exist_ok=True, mode=0o700)
    handle = open(LOCK_ROOT / f"{name}.lock", "a+b")
    try:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as exc:
        handle.close()
        raise HTTPException(status_code=409, detail="Persona is locked by another browser process") from exc
    _PROFILE_LOCKS[name] = handle


def _browser_running(name: str) -> tuple[bool, int | None]:
    process = _PROCESSES.get(name)
    if process and process.poll() is None:
        return True, process.pid
    if process:
        _PROCESSES.pop(name, None)
        _release_profile_lock(name)
    pids = _matching_pids(name)
    return (bool(pids), pids[0] if pids else None)


def _terminate_browser(name: str) -> list[int]:
    process = _PROCESSES.pop(name, None)
    targeted: set[int] = set(_matching_pids(name))
    if process and process.poll() is None:
        targeted.add(process.pid)
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    else:
        for pid in targeted:
            try:
                os.kill(pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline and _matching_pids(name):
        time.sleep(0.1)
    remaining = _matching_pids(name)
    for pid in remaining:
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    _release_profile_lock(name)
    return sorted(targeted)


def _clear_stale_singleton_locks(name: str) -> None:
    directory = _persona_dir(name)
    for filename in ("SingletonLock", "SingletonCookie", "SingletonSocket"):
        try:
            (directory / filename).unlink(missing_ok=True)
        except OSError as exc:
            raise HTTPException(status_code=500, detail="Unable to remove a stale browser lock") from exc


def _safe_url(url: str) -> str:
    if len(url) > 4096:
        raise HTTPException(status_code=422, detail="URL is too long")
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise HTTPException(status_code=422, detail="Only absolute HTTP(S) URLs are allowed")
    return url


def _status(name: str) -> PersonaStatus:
    directory = _persona_dir(name)
    running, pid = _browser_running(name)
    return PersonaStatus(
        name=name,
        meta=_read_meta(name),
        profile_exists=directory.exists(),
        has_session=_has_session(name),
        browser_running=running,
        browser_pid=pid,
    )


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/", response_class=HTMLResponse)
def ui():
    return HTMLResponse((Path(__file__).parent / "templates" / "index.html").read_text(encoding="utf-8"))


@app.get("/static/app.js")
def app_javascript():
    content = (Path(__file__).parent / "static" / "app.js").read_text(encoding="utf-8")
    return Response(content, media_type="application/javascript")


@app.get("/api/personas", response_model=list[PersonaStatus], dependencies=[Auth])
def list_personas():
    with _OPERATIONS_LOCK:
        return [_status(name) for name in _list_personas()]


@app.get("/api/personas/{name}", response_model=PersonaStatus, dependencies=[Auth])
def get_persona(name: str):
    directory = _persona_dir(name)
    if not directory.exists():
        raise HTTPException(status_code=404, detail="Persona not found")
    with _OPERATIONS_LOCK:
        return _status(name)


@app.post("/api/personas", response_model=PersonaStatus, status_code=201, dependencies=[Auth])
def create_persona(body: CreatePersona):
    name = _validate_name(body.name)
    with _OPERATIONS_LOCK:
        directory = _persona_dir(name)
        if directory.exists():
            raise HTTPException(status_code=409, detail="Persona already exists")
        meta = PersonaMeta(name=name, description=body.description, accounts=body.accounts, notes=body.notes)
        _write_meta(name, meta)
        return _status(name)


@app.put("/api/personas/{name}", response_model=PersonaStatus, dependencies=[Auth])
def update_persona(name: str, body: UpdatePersona):
    directory = _persona_dir(name)
    if not directory.exists():
        raise HTTPException(status_code=404, detail="Persona not found")
    with _OPERATIONS_LOCK:
        meta = _read_meta(name)
        if body.description is not None:
            meta.description = body.description
        if body.accounts is not None:
            meta.accounts = body.accounts
        if body.notes is not None:
            meta.notes = body.notes
        _write_meta(name, meta)
        return _status(name)


@app.delete("/api/personas/{name}", status_code=204, dependencies=[Auth])
def delete_persona(name: str):
    directory = _persona_dir(name)
    if not directory.exists():
        raise HTTPException(status_code=404, detail="Persona not found")
    with _OPERATIONS_LOCK:
        _terminate_browser(name)
        if _matching_pids(name):
            raise HTTPException(status_code=409, detail="Browser is still using this persona")
        _acquire_profile_lock(name)
        try:
            shutil.rmtree(directory)
        finally:
            _release_profile_lock(name)
    return Response(status_code=204)


@app.post("/api/personas/{name}/launch", dependencies=[Auth])
def launch_browser(name: str, url: str = "https://example.com"):
    directory = _persona_dir(name)
    if not directory.exists():
        raise HTTPException(status_code=404, detail="Persona not found")
    target = _safe_url(url)
    with _OPERATIONS_LOCK:
        running, pid = _browser_running(name)
        if running:
            return {"status": "already_running", "pid": pid, "persona": name}
        _acquire_profile_lock(name)
        _clear_stale_singleton_locks(name)
        log_path = Path("/tmp") / f"pyplayvnc-{name}.log"
        log_handle = open(log_path, "ab", buffering=0)
        command = [
            CHROMIUM_BIN,
            _profile_arg(name),
            "--password-store=basic",
            "--no-first-run",
            "--no-default-browser-check",
            "--start-maximized",
            target,
        ]
        try:
            process = subprocess.Popen(
                command,
                stdout=log_handle,
                stderr=log_handle,
                env={**os.environ, "DISPLAY": DISPLAY},
                start_new_session=True,
            )
            time.sleep(0.5)
            if process.poll() is not None:
                raise RuntimeError("Chromium exited during startup")
            _PROCESSES[name] = process
            return {"status": "launched", "pid": process.pid, "url": target, "persona": name}
        except Exception as exc:
            _release_profile_lock(name)
            raise HTTPException(status_code=500, detail="Browser launch failed") from exc
        finally:
            log_handle.close()


@app.post("/api/personas/{name}/kill", dependencies=[Auth])
def kill_browser(name: str):
    _persona_dir(name)
    with _OPERATIONS_LOCK:
        killed = _terminate_browser(name)
    return {"status": "killed" if killed else "not_running", "pids": killed}


@app.get("/api/personas/{name}/status", dependencies=[Auth])
def browser_status(name: str):
    _persona_dir(name)
    with _OPERATIONS_LOCK:
        running, pid = _browser_running(name)
        return {"persona": name, "browser_running": running, "pid": pid, "has_session": _has_session(name)}
