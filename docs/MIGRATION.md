# MIGRATION.md — Moving PyPlayVNC to Another Machine

This guide covers moving the entire system — profiles, sessions, and config — to a new
host with zero re-login required.

---

## What Needs to Move

| Item | Location | Required |
|---|---|---|
| Chrome profiles (cookies, sessions) | `profiles/` | ✅ Yes |
| Persona metadata | `profiles/*/persona.yml` | ✅ Yes |
| Manager source | `manager/` | ✅ Yes |
| Container scripts | `container/` | ✅ Yes |
| Compose + Dockerfile | root | ✅ Yes |
| Secrets | `.env` | ✅ Yes (separately) |
| User scripts | `playwright-scripts/` | optional |
| Shared files | `shared/` | optional |

Chrome profile data (`profiles/*/Default/`) is committed to git so it travels with the
repo. You do NOT need a separate backup step for sessions — they are in the repo.

---

## Method 1 — Git (recommended, sessions included)

Chrome sessions are committed to the repo. Cloning or pulling on the new machine
restores everything including login state.

### On old machine

```bash
cd ~/repos/playwright_python_vnc

# Stage everything including profile data
git add profiles/ manager/ container/ docker-compose.yml \
        Dockerfile .env.example .gitignore AGENTS.md README.md docs/

# .env is NOT committed — copy it separately (see below)
git commit -m "checkpoint: full state with sessions"
git push
```

Copy `.env` securely (it contains your API_KEY_HASH):
```bash
scp .env user@new-machine:~/repos/playwright_python_vnc/.env
```

### On new machine

```bash
git clone https://github.com/shashankrawlani/playwright_python_vnc
cd playwright_python_vnc
# .env was copied above — verify it exists
cat .env | grep API_KEY_HASH

docker compose up -d
```

That's it. All personas are restored with their login sessions intact.

---

## Method 2 — Tarball (no git required)

```bash
# On old machine — create archive
cd ~/repos
tar -czf pyplayvnc_$(date +%Y%m%d_%H%M).tar.gz playwright_python_vnc/

# Transfer
scp pyplayvnc_*.tar.gz user@new-machine:~/

# On new machine
cd ~
tar -xzf pyplayvnc_*.tar.gz
cd playwright_python_vnc
docker compose up -d
```

---

## Method 3 — rsync (incremental, good for updates)

```bash
rsync -avz --progress \
  ~/repos/playwright_python_vnc/ \
  user@new-machine:~/repos/playwright_python_vnc/
```

---

## Requirements on New Machine

- Docker Engine + Docker Compose v2
- Port 5900 (VNC) and 8888 (manager) available
- The Docker image will be pulled automatically from Docker Hub on first `docker compose up`

No Python, no Playwright, no Chromium install needed on the host — everything runs
inside the container.

---

## Post-Migration Checklist

```bash
# 1. Verify both containers are running
docker ps | grep -E "playwright_vnc|persona_manager"

# 2. Check personas are visible
curl -H "X-API-Key: $KEY" http://localhost:8888/api/personas

# 3. Check sessions are intact (has_session should be true)
curl -H "X-API-Key: $KEY" http://localhost:8888/api/personas/default/status
curl -H "X-API-Key: $KEY" http://localhost:8888/api/personas/example-persona/status

# 4. Launch a browser and verify login is still active
curl -X POST -H "X-API-Key: $KEY" \
  "http://localhost:8888/api/personas/default/launch?url=https://mail.google.com"
# Connect to VNC :5900 and confirm Gmail is logged in
```

---

## If Sessions Are Lost

Google occasionally invalidates sessions when it detects a new IP or device. If you
get a login prompt after migration:

1. Launch the persona: `POST /api/personas/{name}/launch`
2. Connect to VNC (port 5900)
3. Complete login manually
4. Close Chrome
5. Commit the updated profile: `git add profiles/{name}/ && git commit -m "refresh session"`

---

## Changing the API Key After Migration

If you want a fresh key on the new machine:

```bash
python3 -c "
import secrets, hashlib
k = secrets.token_urlsafe(32)
print('RAW:', k)
print('HASH:', hashlib.sha256(k.encode()).hexdigest())
"
```

Update `.env` with the new `API_KEY_HASH`, then:
```bash
docker compose restart manager
```

Store the new raw key in your password manager and update any AI agent configs.

---

## Notes

- The `shared/` directory is for temporary file exchange and is gitignored. Don't rely
  on it for persistent data.
- `playwright-scripts/` is gitignored. Copy manually if needed.
- Chrome profile data owned by `root` (container user) may require `sudo` to tar on host.
  Use `sudo tar` or run from inside the container if needed.
