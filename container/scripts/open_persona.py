#!/usr/bin/env python3
"""Open a Playwright persistent context for one local persona."""

from __future__ import annotations

import argparse
import fcntl
import os
import re
from pathlib import Path
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright

PERSONA_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--persona", default=os.getenv("PERSONA", "default"))
    parser.add_argument("--url", default="https://example.com")
    parser.add_argument("--headless", action="store_true")
    return parser.parse_args()


def validate(persona: str, url: str) -> tuple[str, str]:
    if not PERSONA_RE.fullmatch(persona):
        raise SystemExit("Invalid persona name")
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise SystemExit("Only absolute HTTP(S) URLs are allowed")
    return persona, url


def main() -> None:
    args = arguments()
    persona, url = validate(args.persona, args.url)
    profiles_root = Path(os.getenv("PROFILES_ROOT", "/app/profiles")).resolve()
    profile = (profiles_root / persona).resolve()
    if profile.parent != profiles_root or not (profile / "persona.yml").is_file():
        raise SystemExit("Persona does not exist")

    lock_root = Path(os.getenv("LOCK_ROOT", "/tmp/pyplayvnc-locks"))
    lock_root.mkdir(parents=True, exist_ok=True, mode=0o700)
    with open(lock_root / f"{persona}.lock", "a+b") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise SystemExit("Persona is already in use") from exc

        with sync_playwright() as playwright:
            context = playwright.chromium.launch_persistent_context(
                str(profile),
                headless=args.headless,
                args=["--password-store=basic", "--no-first-run", "--no-default-browser-check"],
                viewport=None if not args.headless else {"width": 1280, "height": 1024},
            )
            page = context.pages[0] if context.pages else context.new_page()
            page.goto(url, wait_until="domcontentloaded")
            print(f"Loaded: {page.title()}")
            if not args.headless:
                try:
                    page.wait_for_event("close", timeout=0)
                except KeyboardInterrupt:
                    pass
            context.close()


if __name__ == "__main__":
    main()
