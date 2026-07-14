# PyPlayVNC

A local-only, Dockerized Playwright/Chromium environment with persistent, isolated browser personas, a VNC display, and a small authenticated management API.

## Security model

- The manager and VNC ports bind to `127.0.0.1` by default.
- VNC requires a password stored in `secrets/vnc_password`.
- Every persona API route requires an API key; the service refuses to start without a valid SHA-256 verifier.
- The raw API key is kept only in memory by the web UI and is never stored in browser storage.
- Runtime Chrome profiles, `.env`, secrets, shared files, and user automation scripts are excluded from Git and Docker build contexts.
- The service runs as an unprivileged user with all Linux capabilities dropped, the default seccomp profile, `no-new-privileges`, and a read-only root filesystem.
- The Docker socket is not mounted.

This is a local administration tool, not an Internet-facing service. Use SSH forwarding for remote access.

## Components

- Python 3.12 and Playwright 1.61.0
- Playwright Chrome for Testing 149
- Xvfb, Fluxbox, and password-protected x11vnc
- FastAPI persona manager
- Persistent host-mounted profiles

## Quick start

```bash
git clone https://github.com/OWNER/playwright_python_vnc.git
cd playwright_python_vnc
chmod +x pyplayvnc
./pyplayvnc init
```

`init` prints a high-entropy API key once. Save it in a password manager. It stores only the SHA-256 verifier in `.env` and writes a separate VNC password to the ignored `secrets/` directory.

```bash
export PYPLAYVNC_KEY='<raw API key from init>'
./pyplayvnc up
./pyplayvnc status
```

Access locally:

- Manager: `http://127.0.0.1:8888`
- VNC: `127.0.0.1:5900` using the local password in `secrets/vnc_password`

For remote access, tunnel both loopback ports:

```bash
ssh -L 8888:127.0.0.1:8888 -L 5900:127.0.0.1:5900 user@host
```

Do not publish either port directly.

## Personas

Runtime personas live under ignored `profiles/<name>/` directories. The API accepts only 1–64 ASCII letters, digits, underscores, and hyphens. Every browser entry point uses a shared advisory lock so one profile cannot be opened concurrently.

Create through the UI or API:

```bash
curl --fail-with-body \
  -H "X-API-Key: $PYPLAYVNC_KEY" \
  -H 'Content-Type: application/json' \
  -d '{"name":"example","description":"Local example","accounts":[],"notes":""}' \
  http://127.0.0.1:8888/api/personas
```

Open it for manual use:

```bash
./pyplayvnc open example https://example.com
# Connect via VNC, then stop it when finished:
./pyplayvnc kill example
```

Authentication to third-party websites is always a manual user action. PyPlayVNC does not guarantee that a website will accept a containerized browser and does not claim to bypass bot detection.

## Playwright automation

After creating a persona and, if needed, authenticating manually:

```bash
docker compose exec -e PERSONA=example pyplayvnc \
  python3 /app/scripts/open_persona.py --url https://example.com --headless
```

Custom scripts should stay in the ignored `playwright-scripts/` directory or another private project. Never print cookies, tokens, profile database contents, or API keys.

## Lifecycle

```bash
./pyplayvnc up
./pyplayvnc status
./pyplayvnc logs
./pyplayvnc down
```

Stopping/removing the container does not delete host-mounted profiles. Deleting a persona through the API permanently removes that persona's local directory after its browser is stopped.

## Local profile permissions

The image defaults to UID/GID 1000. `pyplayvnc init` records the current user's UID/GID in `.env`. If upgrading from an older root-running image, stop all containers and fix ownership once:

```bash
sudo chown -R "$(id -u):$(id -g)" profiles shared
chmod 700 profiles shared
```

## Migration and history safety

- [Safe migration](docs/MIGRATION.md)
- [History remediation](docs/HISTORY_REMEDIATION.md)

Never commit `profiles/`. Chrome profile files contain live credentials. `git ls-files profiles/` must return no output before any push.

## Dependency and image policy

- The Playwright base image is pinned by tag and digest.
- Python dependencies are pinned with hashes in `manager/requirements.lock`.
- Compose builds the checked-out source instead of silently relying on a stale `latest` image.
- Release automation should publish immutable version and commit-SHA tags; `latest` is not a deployment pin.

Regenerate dependencies only after review:

```bash
pip-compile --strip-extras --generate-hashes \
  --output-file=manager/requirements.lock manager/requirements.in
pip-audit -r manager/requirements.lock
```

## Development checks

```bash
python3 -m pytest -q
bash -n pyplayvnc container/*.sh
docker compose config --quiet
docker compose build --pull
```

## Public-release checklist

1. `git ls-files profiles/ .env secrets/` returns nothing.
2. Secret and history scans pass.
3. Tests and image smoke tests pass.
4. Published image digest and package versions match the release.
5. Historical PII has been removed from every ref before public visibility is enabled.
