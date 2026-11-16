"""Reproduce a Mini App reload in a real browser.

Reloading the page is what the user reported as "the Hermes auth page
appeared". This script opens the page exactly like Telegram's WebView does
(URL fragment carrying a signed initData), then reloads it and records every
request the browser makes — so we can see whether anything navigates to
/login.
"""
from __future__ import annotations

import sys
from pathlib import Path
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).resolve().parent))

from telegram_auth import resolve_bot_token  # noqa: E402
from verify_browser import CHROME, PAGE, make_init_data  # noqa: E402


def main() -> int:
    from playwright.sync_api import sync_playwright

    init_data = make_init_data(resolve_bot_token())
    url = PAGE + "#tgWebAppData=" + quote(init_data, safe="")

    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=CHROME, args=["--no-sandbox"])
        page = browser.new_page(viewport={"width": 390, "height": 844})
        requests: list[str] = []
        page.on("request", lambda r: requests.append(r.url))
        errors: list[str] = []
        page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)

        page.goto(url, wait_until="networkidle", timeout=45000)
        print("after load  -> title:", page.title())
        print("after load  -> url  :", page.url.split("#")[0])
        print("after load  -> entries:", page.evaluate("document.querySelectorAll('#tree *').length"))

        requests.clear()
        page.reload(wait_until="networkidle", timeout=45000)
        print("\nafter reload -> title:", page.title())
        print("after reload -> url  :", page.url.split("#")[0])
        print("after reload -> fragment kept:", "#tgWebAppData" in page.url)
        print("after reload -> entries:", page.evaluate("document.querySelectorAll('#tree *').length"))

        print("\nrequests during reload:")
        for r in requests:
            print("  ", r.split("?")[0])

        login_hits = [r for r in requests if "/login" in r]
        print("\nrequests hitting /login:", len(login_hits))
        print("console errors:", errors[:5])

        browser.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
