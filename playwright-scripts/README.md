# Private Playwright scripts

This directory is ignored because automation can contain private URLs, selectors, account identifiers, or output. Keep reusable public examples generic and free of credentials.

Use the locked helper in the running container:

```bash
docker compose exec -e PERSONA=example pyplayvnc \
  python3 /app/scripts/open_persona.py --url https://example.com --headless
```

Never log cookies, authorization headers, session storage, local storage, or profile database contents.
