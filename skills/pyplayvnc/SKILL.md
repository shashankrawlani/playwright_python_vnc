---
name: pyplayvnc
description: >
  Operate a local PyPlayVNC browser stack with personas, VNC login, and
  Playwright MCP sidecars. Use this skill whenever the user wants to open or
  switch a browser persona, inspect or recover a live browser session, confirm a
  website works in VNC, automate a persona with Playwright, start or stop a
  per-persona MCP sidecar, or debug browser/profile lifecycle issues in a local
  homelab. Also use it when the user asks to "open Gmail", "switch persona",
  "show the browser works", "use MCP", "run browser automation", or "check the
  persona manager."
---

# PyPlayVNC

PyPlayVNC is a local-only browser automation stack. It provides:

- a manager API for persona lifecycle
- a VNC browser for human login and visual verification
- a Playwright MCP sidecar per persona for agentic automation
- persistent browser profiles stored on the host

Treat every browser profile as credential-bearing state. Do not expose it
publicly, do not print cookies or tokens, and do not copy profile data into the
skill outputs.

## What this skill should do

Use PyPlayVNC when the user wants to:

- create, open, inspect, switch, or kill a browser persona
- confirm that a site loads in the VNC browser
- log into a site manually in the browser
- run Playwright against an existing persona profile
- start, stop, or troubleshoot a per-persona MCP sidecar
- move between human browsing and agent browsing safely

## Operating model

There are two browser paths:

1. Live browser path
   - Used by humans in VNC.
   - Controlled by the persona manager API.
   - Starts a Chromium instance against the live persona profile.

2. MCP sidecar path
   - Used by agents and Playwright MCP clients.
   - Starts as a separate sidecar for one persona at a time.
   - Uses a seeded private copy of that persona profile.
   - Must not overwrite or leak the live persona profile.

Keep those paths separate. If the user wants both human browsing and agent
automation, use the live browser for the human and the MCP sidecar for the
agent.

## Safe workflow

When a user asks to work with a persona, follow this order:

1. Verify the persona exists.
2. Check whether the live browser is already running.
3. Open the browser in VNC if the task needs a human login or visual check.
4. Use the browser to complete the login or confirm the page.
5. Stop or switch the live browser when handing the persona to automation.
6. Start the MCP sidecar for the same persona when the user wants agent access.
7. Point the MCP client at the local SSE URL returned by the tool.

If the user wants a browser demo, prefer a simple site such as `example.com`
first. Only use a sensitive site like Gmail when the user explicitly asks for it.

## Typical commands

Use the repository CLI for lifecycle actions:

```bash
./pyplayvnc up
./pyplayvnc status
./pyplayvnc open <persona> https://example.com
./pyplayvnc kill <persona>
./pyplayvnc mcp start <persona>
./pyplayvnc mcp status
./pyplayvnc mcp stop <persona>
```

Use the manager API when you need explicit persona state:

```bash
curl -H "X-API-Key: $PYPLAYVNC_KEY" http://localhost:8888/api/personas
curl -H "X-API-Key: $PYPLAYVNC_KEY" http://localhost:8888/api/personas/<name>/status
curl -X POST -H "X-API-Key: $PYPLAYVNC_KEY" \
  "http://localhost:8888/api/personas/<name>/launch?url=https://example.com"
curl -X POST -H "X-API-Key: $PYPLAYVNC_KEY" \
  http://localhost:8888/api/personas/<name>/kill
```

## Headless automation

When the user asks for browser automation against a persona profile, prefer the
repository helper:

```bash
docker compose exec -e PERSONA=<name> pyplayvnc \
  python3 /app/scripts/open_persona.py --url https://example.com --headless
```

Use the persona profile only after confirming it has a session if the target
site needs one.

## MCP sidecars

The MCP sidecar is the preferred way to give an agent browser access without
sharing the live VNC browser. Start one per persona and keep the port local.

Important rules:

- Use one sidecar per persona.
- Do not point MCP at the live browser profile.
- Start the sidecar only after the persona profile exists.
- Treat the returned SSE URL as local-only.

If the user asks to "use MCP", "attach browser automation", or "let the agent
drive this persona", start the sidecar and hand the client the local SSE URL.

## Troubleshooting

If the browser seems stuck:

- Check whether the persona is already in use.
- Kill the live browser before starting a conflicting session.
- Remove stale singleton locks only as part of the repository's own cleanup
  flow, not as a general habit.
- If the user can see the browser in VNC but automation cannot connect, use the
  MCP sidecar rather than trying to reuse the live browser process.

If a site asks for login again, that is normal after profile migration or site
security changes. Use VNC for manual login and then hand the persona back to the
MCP sidecar if needed.
