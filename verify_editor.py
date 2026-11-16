"""Drive the Mini App editor in a real browser: open a file, edit it, save.

This is the part the phone screenshot did not cover — the screenshot showed
the file tree, never the editor. This script opens the tree, clicks a
Markdown file, types into the textarea, saves, and then re-reads the file
through the API to prove the write really landed.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).resolve().parent))

from telegram_auth import resolve_bot_token  # noqa: E402
from verify_browser import CHROME, PAGE, make_init_data  # noqa: E402

TARGET_NAME = "miniapp-editor-check.md"
TARGET_DIR = os.environ.get("MINIAPP_EDITOR_DIR") or (
    Path(tempfile.gettempdir()) / "tgmini-editor-check"
)


def main() -> int:
    from playwright.sync_api import sync_playwright

    init_data = make_init_data(resolve_bot_token())
    url = PAGE + "#tgWebAppData=" + quote(init_data, safe="")

    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=CHROME, args=["--no-sandbox"])
        page = browser.new_page(
            viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True
        )
        console: list[str] = []
        page.on("console", lambda m: console.append(f"[{m.type}] {m.text}"))
        page.on("pageerror", lambda e: console.append(f"[pageerror] {e}"))
        page.goto(url, wait_until="networkidle", timeout=45000)

        # Navigate to the scratch directory through the tree. The match must be
        # exact: a substring match on "cache" would hit "audio_cache" first.
        def open_entry(name: str) -> bool:
            return bool(
                page.evaluate(
                    """(name) => {
                      const el = [...document.querySelectorAll('.entry .name')]
                        .find(n => n.textContent.trim() === name);
                      if (!el) return false;
                      el.closest('.entry').click();
                      return true;
                    }""",
                    name,
                )
            )

        # Create the file BEFORE navigating: a reload resets the client-side
        # path back to the root, so the tree has to be walked again.
        target = Path(TARGET_DIR) / TARGET_NAME
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("# original\n", encoding="utf-8")

        # Walk the tree by PATH SEGMENTS relative to the managed root, so the
        # check does not depend on any particular directory layout. The root
        # itself is not part of the tree, so its segments are dropped.
        root = page.inner_text("#path").strip()
        segments = [
            p for p in Path(TARGET_DIR).parts
            if p not in ("/", "") and str(TARGET_DIR).startswith(root)
            and p not in Path(root).parts
        ]
        for name in segments:
            if not open_entry(name):
                print(f"entry not found: {name}; path is", page.inner_text("#path"))
                return 1
            page.wait_for_timeout(500)
        print("path after navigation:", page.inner_text("#path"))

        if not open_entry(TARGET_NAME):
            print("target file not found in the tree; path is", page.inner_text("#path"))
            return 1
        # The file is fetched over the network: wait for the editor to actually
        # open instead of guessing a delay.
        try:
            page.wait_for_function(
                "document.getElementById('editor').classList.contains('open')"
                " && document.getElementById('text').value.length > 0",
                timeout=20000,
            )
        except Exception as exc:  # noqa: BLE001
            print("editor did not open:", exc)
            return 1
        page.wait_for_timeout(200)

        print("editor open:", page.evaluate("document.getElementById('editor').classList.contains('open')"))
        print("textarea value:", page.input_value("#text").strip())
        print("save button enabled:", not page.evaluate("document.getElementById('save').disabled"))
        print("preview button enabled:", not page.evaluate("document.getElementById('previewToggle').disabled"))

        page.fill("#text", "# edited by the editor check\n\nsecond line\n")
        page.click("#save")
        page.wait_for_timeout(900)
        print("status after save:", page.inner_text("#status"))
        print("file on disk:", target.read_text(encoding="utf-8").strip().replace("\n", " | "))

        # The preview renders Markdown when the file is Markdown.
        page.click("#previewToggle")
        page.wait_for_timeout(400)
        print("preview visible:", page.evaluate("document.getElementById('preview').classList.contains('open')"))
        print("preview html starts:", page.inner_html("#preview")[:80])

        print("console errors:", [c for c in console if "error" in c.lower()][:5])
        browser.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
