# 🌀 PyPlayVNC - Lightweight Container for Playwright, Python, and VNC

## DockerHub: [shashankrawlani/playwright_python_vnc](https://hub.docker.com/repository/docker/shashankrawlani/playwright_python_vnc)

**PyPlayVNC** is a Dockerized environment for visual browser automation using [Playwright](https://playwright.dev/python/), with Python scripting, a virtual display, and VNC access for remote debugging. It’s perfect for tasks like:

- Headless browser automation with GUI fallback
- Multi-profile browser testing
- Visual debugging via VNC

> 🐍 Python + 🎭 Playwright + 🖥️ VNC + 📦 Xvfb + 🎛️ Fluxbox

---

## 🚀 Features

- **🐍 Python** — for scripting and automation.
- **🎭 Playwright** — supports Chromium, Firefox, and WebKit.
- **🖥️ VNC** — connect to a visual session of your headless browser.
- **📦 Xvfb** — provides a virtual display for browser rendering.
- **🎛️ Fluxbox** — lightweight window manager for the VNC session.
- **🧩 Modular Entry Point** — `entry_point.sh` now uses shell functions.
- **📂 Mountable User Profiles** — make `/app/user_data` persistent via volumes.
- **🧠 Monkey Patch Option** — replace `launch()` globally with `launch_persistent_context()`.

---

## 📂 Directory Structure

- `/app/user_data`: Browser profiles and persistent session data.
- `/shared`: Shared volume mount point between host and container.

---

## 🛠️ Environment Variables

| Variable        | Default          | Description                         |
| --------------- | ---------------- | ----------------------------------- |
| `DISPLAY`       | `:99`            | Virtual display ID used by Xvfb     |
| `USER_DATA_DIR` | `/app/user_data` | Stores browser session/profile data |

---

## ✅ Startup Checks

On container startup, the following checks are performed automatically:

- 🐍 **Python** version check
- 🎭 **Playwright** installation (Python & CLI)
- 📦 Xvfb virtual display launch
- 🖥️ x11vnc (VNC server) startup
- 🎛️ Fluxbox window manager startup

---

## 🧪 Usage

### 1. Pull the Docker Image

```bash
docker pull shashankrawlani/playwright_python_vnc:latest
```

### 2. Run the Container

```bash
docker run -it --rm   -p 5900:5900   -v $(pwd)/shared:/shared   shashankrawlani/playwright_python_vnc:latest
```

> ✅ **Port 5900** is exposed for VNC access.  
> ✅ **`/shared`** is a mounted volume between host and container.

---

## 🔍 Access the VNC Server

1. Install a VNC viewer (e.g., [RealVNC Viewer](https://www.realvnc.com/en/connect/download/viewer/)).
2. Connect to `localhost:5900`.
3. You’ll see the container's lightweight desktop environment.

---

## 🧩 Customize Browser Profiles

- Add or modify browser profiles under `/app/user_data`.
- Great for testing with persistent sessions, cookies, and localStorage.

---

## 🔐 Ensuring Persistent Browser Profiles in /app/user_data

To make Playwright always use the `/app/user_data` directory for persistent browser profiles, follow these practices:

- By default, Playwright does not persist sessions unless explicitly instructed.
- Use `launch_persistent_context()` for persistent sessions (cookies, local storage, installed extensions, etc.).

### ✅ Recommended Directory

This container sets the default profile path using an environment variable:

```bash
USER_DATA_DIR=/app/user_data
```

---

## 🧱 Option 1: Basic Persistent Context (Sync Example)

```python
from playwright.sync_api import sync_playwright
import os

USER_DATA_DIR = os.getenv("USER_DATA_DIR", "/app/user_data")

with sync_playwright() as p:
    browser = p.chromium.launch_persistent_context(
        USER_DATA_DIR,
        headless=False,
        args=["--start-maximized"]
    )
    page = browser.new_page()
    page.goto("https://example.com")
    browser.close()
```

---

## ⚙️ Option 2: Wrapper Utility (Reusable Function)

```python
# utils/playwright_browser.py
import os
from playwright.sync_api import sync_playwright

def get_browser():
    USER_DATA_DIR = os.getenv("USER_DATA_DIR", "/app/user_data")
    playwright = sync_playwright().start()
    context = playwright.chromium.launch_persistent_context(
        USER_DATA_DIR,
        headless=False,
        args=["--start-maximized"]
    )
    return context
```

**Usage:**

```python
from utils.playwright_browser import get_browser

browser = get_browser()
page = browser.new_page()
page.goto("https://example.com")
browser.close()
```

---

## 🐒 Option 3: Monkey Patch launch() Globally

```python
from playwright.sync_api import sync_playwright
import os

def monkey_patch_launch(playwright):
    USER_DATA_DIR = os.getenv("USER_DATA_DIR", "/app/user_data")

    def _patched_launch(*args, **kwargs):
        return playwright.chromium.launch_persistent_context(
            USER_DATA_DIR,
            headless=kwargs.get("headless", True),
            args=kwargs.get("args", [])
        )

    playwright.chromium.launch = _patched_launch
    return playwright

with sync_playwright() as p:
    p = monkey_patch_launch(p)
    browser = p.chromium.launch()  # Actually uses launch_persistent_context()
    page = browser.new_page()
    page.goto("https://example.com")
    browser.close()
```

---

## 🌀 Option 4: Async Version

```python
import os
import asyncio
from playwright.async_api import async_playwright

async def main():
    USER_DATA_DIR = os.getenv("USER_DATA_DIR", "/app/user_data")

    async with async_playwright() as p:
        browser = await p.chromium.launch_persistent_context(
            USER_DATA_DIR,
            headless=False,
            args=["--start-maximized"]
        )
        page = await browser.new_page()
        await page.goto("https://example.com")
        await browser.close()

asyncio.run(main())
```

---

## 📝 Notes

- Requires Docker and a VNC client installed on your host.
- Based on `mcr.microsoft.com/playwright/python:v1.51.0-noble`, with Python & Playwright pre-installed.
- Includes system dependencies for headless + GUI operation.
- Always use `launch_persistent_context()` if you want to retain cookies, sessions, logins, etc.
- Use the `USER_DATA_DIR` environment variable to customize the directory outside your code logic (e.g., via Dockerfile).
- **Modularized Shell Startup**: You can now run internal tools like `start_xvfb`, `start_vnc`, and `start_fluxbox` directly in the container shell.
- Never use both `launch()` and `launch_persistent_context()` for the same purpose—they behave differently.

---

## 🎉 Final Thoughts

Enjoy seamless and visual browser automation with:

> 🐍 Python + 🎭 Playwright + 🖥️ VNC + 📦 Xvfb + 🎛️ Fluxbox