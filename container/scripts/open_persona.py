#!/usr/bin/env python3
"""
open_persona.py — Open a Playwright browser session using a saved persona profile.

Prerequisites:
    1. Login manually first using run_browser.sh (just once per persona)
    2. Run this script to reuse that saved session via Playwright

Usage:
    # Inside the container:
    PERSONA=persona1 python3 /app/scripts/open_persona.py
    PERSONA=persona1 python3 /app/scripts/open_persona.py --url https://gmail.com
    PERSONA=persona1 python3 /app/scripts/open_persona.py --headless

    # From host (exec into running container):
    docker compose exec -e PERSONA=persona1 playwright-vnc \
        python3 /app/scripts/open_persona.py --url https://gmail.com
"""

import argparse
import os
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright, BrowserContext, Page


# ─────────────────────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────────────────────

PERSONA = os.getenv("PERSONA", "default")
PROFILES_ROOT = Path(os.getenv("PROFILES_ROOT", "/app/profiles"))
PROFILE_DIR = PROFILES_ROOT / PERSONA


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Open a Playwright session for a persona.")
    parser.add_argument(
        "--url",
        default="https://mail.google.com",
        help="URL to open (default: https://mail.google.com)",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Run in headless mode (no visible window)",
    )
    parser.add_argument(
        "--persona",
        default=None,
        help="Override PERSONA env var",
    )
    return parser.parse_args()


# ─────────────────────────────────────────────────────────────
# Anti-detection init script
# ─────────────────────────────────────────────────────────────

STEALTH_SCRIPT = """
    // Mask navigator.webdriver — the most common bot detection signal
    Object.defineProperty(navigator, 'webdriver', { get: () => undefined });

    // Restore chrome runtime object (missing in Playwright Chromium by default)
    window.chrome = { runtime: {} };

    // Spoof permissions query to look like a real browser
    const originalQuery = window.navigator.permissions.query;
    window.navigator.permissions.query = (parameters) =>
        parameters.name === 'notifications'
            ? Promise.resolve({ state: Notification.permission })
            : originalQuery(parameters);
"""


# ─────────────────────────────────────────────────────────────
# Browser launch
# ─────────────────────────────────────────────────────────────

def get_context(playwright, profile_dir: Path, headless: bool) -> BrowserContext:
    """Launch Chromium with persistent context for the given profile directory."""

    if not profile_dir.exists():
        print(f"❌ Profile directory not found: {profile_dir}")
        print(f"   Run `run_browser.sh` first to create and login to this persona.")
        sys.exit(1)

    context = playwright.chromium.launch_persistent_context(
        str(profile_dir),
        headless=headless,
        args=[
            "--no-sandbox",
            "--disable-setuid-sandbox",
            "--disable-blink-features=AutomationControlled",
            "--disable-infobars",
            "--disable-dev-shm-usage",
            "--no-first-run",
            "--no-default-browser-check",
            "--start-maximized",
        ],
        viewport=None,          # use --start-maximized instead
        ignore_https_errors=False,
    )

    # Apply stealth patches to every new page
    context.add_init_script(STEALTH_SCRIPT)

    return context


# ─────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────

def main() -> None:
    args = parse_args()

    # Allow --persona flag to override env var
    persona = args.persona or PERSONA
    profile_dir = PROFILES_ROOT / persona

    print(f"\n🧑 Persona     : {persona}")
    print(f"📂 Profile dir : {profile_dir}")
    print(f"🌐 URL         : {args.url}")
    print(f"👁️  Headless    : {args.headless}\n")

    with sync_playwright() as pw:
        context = get_context(pw, profile_dir, headless=args.headless)

        page: Page = context.new_page()
        page.goto(args.url, wait_until="domcontentloaded")

        print(f"✅ Loaded: {page.title()}")
        print("   Session is live. Press Ctrl+C or close the browser to exit.\n")

        # Keep the session open — useful for manual inspection via VNC,
        # or replace this block with your automation logic.
        try:
            page.wait_for_event("close", timeout=0)  # wait indefinitely
        except KeyboardInterrupt:
            pass
        finally:
            context.close()
            print("👋 Session closed. Profile saved.")


if __name__ == "__main__":
    main()
