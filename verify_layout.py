"""Measure the Mini App layout on a phone-sized viewport.

The stylesheet gives the tree ``flex: 0 0 42%``, which on a 390 px phone
leaves ~164 px for file names — and the editor pane sits beside it even
before a file is opened. This script measures the real geometry instead of
assuming it.
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
        page = browser.new_page(
            viewport={"width": 390, "height": 844},
            is_mobile=True,
            has_touch=True,
        )
        page.goto(url, wait_until="networkidle", timeout=45000)

        geom = page.evaluate(
            """() => {
              const t = document.getElementById('tree');
          const e = document.getElementById('editor');
          const tr = t.getBoundingClientRect();
          const er = e.getBoundingClientRect();
          const names = [...document.querySelectorAll('.entry .name')]
                             .map(n => n.textContent);
          const clipped = [...document.querySelectorAll('.entry .name')]
                             .filter(n => n.scrollWidth > n.clientWidth + 1)
                             .map(n => n.textContent);
          return {
            viewport: window.innerWidth,
            treeWidth: Math.round(tr.width),
            treeHeight: Math.round(tr.height),
            treeScrollable: t.scrollHeight > t.clientHeight + 1,
            editorWidth: Math.round(er.width),
            editorDisplay: getComputedStyle(e).display,
            entries: names.length,
            clippedNames: clipped.length,
            clippedSample: clipped.slice(0, 5),
          };
        }"""
        )
        for key, value in geom.items():
            print(f"{key}: {value}")

        browser.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
