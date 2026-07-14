# playwright-scripts/

Drop your Playwright automation scripts here.

Scripts in this directory are **not committed** (excluded by `.gitignore` outputs).
They run inside the container against a specific persona's saved session:

```bash
docker compose exec -e PERSONA=persona1 playwright-vnc \
    python3 /app/playwright-scripts/your_script.py
```

Use `container/scripts/open_persona.py` as a base template.
