# PyPlayVNC

A local-only, Dockerized Playwright/Chromium environment with persistent, isolated browser personas, a VNC display, and a small authenticated management API.

## Security model

- The manager and VNC ports bind to `127.0.0.1` by default.
- VNC requires a password stored in `secrets/vnc_password`.
- Every persona API route requires an API key; the service refuses to start without a valid SHA-256 verifier.
- The raw API key is kept only in memory by the web UI and is never stored in browser storage.
- Runtime Chrome profiles, `.env`, secrets, shared files, and user automation scripts are excluded from Git and Docker build contexts.
- The service and Chromium browser run as an unprivileged user with a read-only root filesystem and Docker's default seccomp profile.
- Compose drops every Linux capability, then restores only `SETUID`, `SETGID`, `SYS_CHROOT`, and `SYS_ADMIN` so Chromium's root-owned setuid helper can create its PID/network sandbox on hosts that disable unprivileged user namespaces. Chromium drops those setup privileges; the running browser has no effective capabilities.
- `SYS_ADMIN` is a broad capability and `no-new-privileges` is intentionally incompatible with this fallback sandbox. Keep this stack local-only and do not weaken the remaining controls.
- The Docker socket is not mounted.

This is a local administration tool, not an Internet-facing service. By default,
the published ports bind only to the homelab LAN static IP and the current
Tailscale IP, so you can reach them from `192.168.0.121` or over Tailscale
without exposing `0.0.0.0`.

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

## Installable Skill

This repo ships a sanitized, installable skill bundle in [`skills/`](/home/homelab/repos/playwright_python_vnc/skills).
Install the bundled PyPlayVNC skill with:

```bash
npx skills add ./skills --skill pyplayvnc --copy -y
```

`init` prints a high-entropy API key once. Save it in a password manager. It stores only the SHA-256 verifier in `.env` and writes a separate VNC password to the ignored `secrets/` directory.

By default, `init` writes only the API key hash into `.env`. If you want the raw API key and VNC password written locally too, add `--write-env`.

Infisical is the recovery path for all secrets:

- `API_KEY_HASH`
- `PYPLAYVNC_KEY`
- `VNC_PASSWORD`

If those local files are missing, `./pyplayvnc up` will pull them from Infisical before starting the container.

If you want the generated secrets copied into Infisical as well, run:

```bash
PYPLAYVNC_INFISICAL_PROJECT_ID='<project-id>' ./pyplayvnc init --push-infisical
```

If you also want the raw values written to the local `.env` file for convenience, add `--write-env`:

```bash
PYPLAYVNC_INFISICAL_PROJECT_ID='<project-id>' ./pyplayvnc init --write-env --push-infisical
```

That writes:

- `API_KEY_HASH` for the container
- `PYPLAYVNC_KEY` for the dashboard API
- `VNC_PASSWORD` for the VNC client

The raw values are useful for local operators and Infisical sync, but they are not required by the container at runtime.

To rotate the API key and VNC password later, run:

```bash
./pyplayvnc rotate
```

Add `PYPLAYVNC_INFISICAL_PROJECT_ID='<project-id>' ./pyplayvnc rotate --push-infisical` if you want the refreshed secrets copied to Infisical too.

To rehydrate local files from Infisical later:

```bash
PYPLAYVNC_INFISICAL_PROJECT_ID='<project-id>' ./pyplayvnc sync
```

```bash
export PYPLAYVNC_KEY='<raw API key from init>'
./pyplayvnc up
./pyplayvnc status
```

Access locally:

- Manager: `http://127.0.0.1:8888`
- VNC: `127.0.0.1:5900` using the local password in `secrets/vnc_password`

For LAN or Tailscale access, use the published host IPs:

- Manager: `http://192.168.0.121:8888` or `http://100.88.246.85:8888`
- VNC: `192.168.0.121:5900` or `100.88.246.85:5900`

If you prefer SSH forwarding, tunnel both ports instead:

```bash
ssh -L 8888:127.0.0.1:8888 -L 5900:127.0.0.1:5900 user@host
```

Do not publish either port on `0.0.0.0`.

## Playwright MCP Sidecars

For agentic browser automation, run a separate Playwright MCP sidecar per
persona. The sidecar uses the existing persona profile under
`profiles/<persona>/` as its seed, then works from its own private copy under
`.mcp/profiles/<persona>/`. That keeps VNC/manual use and MCP automation from
fighting over Chrome's profile lock.
The sidecar gets a dynamic local port in the `8931-8999` range.

Start it after the persona has been created and logged in once:

```bash
./pyplayvnc mcp start gmail_automation
./pyplayvnc mcp status
```

If you need a fixed port for a specific persona, you can request one:

```bash
./pyplayvnc mcp start gmail_automation --port 8935
```

Stop it when you are done:

```bash
./pyplayvnc mcp stop gmail_automation
```

The MCP client should point at the returned local SSE URL, for example
`http://127.0.0.1:8931/sse`.

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
