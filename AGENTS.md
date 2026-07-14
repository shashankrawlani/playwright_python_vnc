# Agent guidance for PyPlayVNC

PyPlayVNC controls local persistent browser profiles. Treat every runtime profile as credential material.

## Before acting

1. Work from the repository root.
2. Read the target persona's local `profiles/<name>/persona.yml` without exposing its contents outside the host.
3. Check status and do not start a second browser for an active persona.
4. Never infer an account from a persona name.

## Approved lifecycle

```bash
./pyplayvnc up
PYPLAYVNC_KEY='<operator-provided key>' ./pyplayvnc status
PYPLAYVNC_KEY='<operator-provided key>' ./pyplayvnc open <persona> https://example.com
PYPLAYVNC_KEY='<operator-provided key>' ./pyplayvnc kill <persona>
./pyplayvnc down
```

The raw API key must come from the operator's secure runtime environment. Do not write it to source files, logs, commands that will be committed, chat messages, or agent memory.

## Isolation requirements

- Persona names must match `^[A-Za-z0-9_-]{1,64}$`.
- One persona maps to one isolated profile directory.
- Never run two browser processes against one profile.
- Use the manager API/CLI or the supplied locked scripts; do not bypass profile locking.
- Login to third-party services is manual through VNC. Do not automate credential entry.
- Never read, copy, log, summarize, or transmit cookies, token stores, login databases, browser history, or session artifacts.
- Never delete a persona without explicit operator confirmation.

## Network requirements

VNC and the manager bind to host loopback. For a remote operator, recommend an SSH tunnel. Do not change bindings to `0.0.0.0`, disable VNC authentication, or expose the service through a public ingress.

## Repository safety

The following are local-only and must never be committed or included in an image:

- `.env` and `secrets/`
- `profiles/`
- `shared/`
- private automation under `playwright-scripts/`

Before a push, verify:

```bash
git ls-files profiles/ .env secrets/
git status --short
docker compose config --quiet
```

The first command must print nothing. Browser profiles must be migrated only through encrypted/private transfer as documented in `docs/MIGRATION.md`.

## API behavior

- `/health` is intentionally unauthenticated and returns no sensitive data.
- All `/api/*` routes require `X-API-Key`.
- A missing or malformed `API_KEY_HASH` prevents service startup.
- API documentation endpoints are disabled in production.
- Only absolute HTTP(S) launch URLs are accepted.

If a request returns 401/403, stop and ask the operator to supply the correct key securely. Do not brute-force or retry blindly.
