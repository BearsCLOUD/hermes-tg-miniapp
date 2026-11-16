"""Real-browser check of the Telegram Mini App page.

Emulates Telegram's WebView: the SDK reads initData from the URL fragment
(#tgWebAppData=...), then the script reads what the page actually rendered and
captures console errors.

The page URL points at a live Hermes dashboard; set ``MINIAPP_PAGE`` to point
the check at another instance.

Run with a venv that has playwright:
    python verify_browser.py
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import sys
import time
from urllib.parse import quote, urlencode

PAGE = os.environ.get(
    "MINIAPP_PAGE",
    "http://127.0.0.1:8080/dashboard-plugins/telegram-miniapp/index.html",
)

# The Playwright build installed in this image; the npm package version does
# not always match the browser revision, so the binary path is explicit.
# Override with CHROMIUM_PATH when running elsewhere.
CHROME = os.environ.get("CHROMIUM_PATH", "")


def resolve_bot_token() -> str:
    from hermes_cli.config import get_env_value_prefer_dotenv

    return (get_env_value_prefer_dotenv("TELEGRAM_BOT_TOKEN") or "").strip()


def make_init_data(token: str, user_id: str = "123456789") -> str:
    fields = {
        "auth_date": str(int(time.time())),
        "query_id": "AAH_browser_check",
        "user": json.dumps({"id": user_id, "first_name": "Live", "username": "live"}),
    }
    check = "\n".join(f"{k}={fields[k]}" for k in sorted(fields))
    secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    fields["hash"] = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    return urlencode(fields)


def main() -> int:
    from playwright.sync_api import sync_playwright

    init_data = make_init_data(resolve_bot_token())
    only_local_sdk = "--no-sdk" in sys.argv
    rc = 0

    with sync_playwright() as p:
        launch_kwargs: dict[str, object] = {"args": ["--no-sandbox"]}
        if CHROME:
            launch_kwargs["executable_path"] = CHROME
        browser = p.chromium.launch(**launch_kwargs)  # type: ignore[arg-type]
        page = browser.new_page(
            viewport={"width": 390, "height": 844},
            is_mobile=True,
            has_touch=True,
            device_scale_factor=3,
        )
        console: list[str] = []
        page.on("console", lambda msg: console.append(f"[{msg.type}] {msg.text}"))
        page.on("pageerror", lambda err: console.append(f"[pageerror] {err}"))

        if only_local_sdk:
            # Simulate a network where telegram.org is unreachable: the CDN
            # script never loads, so the page must read initData itself.
            page.route(
                "**://telegram.org/**",
                lambda route: route.abort(),
            )

        # Emulate Telegram's WebView exactly: the SDK reads initData from the
        # URL fragment (#tgWebAppData=...) and parses it as a query string, so
        # the whole initData must be percent-encoded (its own '&' separators
        # would otherwise split it). The real SDK overwrites any pre-set
        # Telegram.WebApp object, so no shim is injected.
        page.goto("about:blank")
        page.goto(
            PAGE + "#tgWebAppData=" + quote(init_data, safe=""),
            wait_until="networkidle",
            timeout=45000,
        )
        page.wait_for_timeout(2500)

        print("=== scenario:", "SDK from CDN blocked" if only_local_sdk else "SDK available")
        print("title:", page.title())
        print("status text:", page.locator("#status").inner_text())
        print("path text:", page.locator("#path").inner_text())
        tree_count = page.locator("#tree .entry").count()
        print("tree entries:", tree_count)
        if tree_count:
            print("first entry:", page.locator("#tree .entry .name").first.inner_text())
        sdk_loaded = page.evaluate("!!(window.Telegram && window.Telegram.WebApp)")
        print("sdk object present:", sdk_loaded)

        errors = [line for line in console if "[error]" in line or "[pageerror]" in line]
        print("console errors:", len(errors))
        for line in errors:
            print("  ", line)

        browser.close()

    if tree_count == 0:
        print("FAIL: the file tree did not render")
        rc = 1
    else:
        print("OK: the Mini App rendered the file tree")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
