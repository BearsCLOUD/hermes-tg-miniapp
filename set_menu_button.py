"""Install the chat menu button that opens the Mini App.

Telegram has no plugin hook for the menu button: it is a Bot API call
(``setChatMenuButton``) with a ``web_app`` payload. This script sets it, so
the Mini App is reachable in one tap from the chat and no command is needed.

By default it sets the button for every chat the bot is used in (the default
menu button, which Telegram shows next to the composer). Pass ``--chat-id``
to set it for one chat only.

Usage:
    python set_menu_button.py
    python set_menu_button.py --chat-id 123456789
    python set_menu_button.py --clear          # back to the command list
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from telegram_bridge import _mini_app_url  # noqa: E402


def _bot_token() -> str:
    from hermes_cli.config import get_env_value_prefer_dotenv

    return (get_env_value_prefer_dotenv("TELEGRAM_BOT_TOKEN") or "").strip()


def _call(method: str, payload: dict | None = None) -> dict:
    token = _bot_token()
    if not token:
        raise SystemExit("TELEGRAM_BOT_TOKEN is not configured")
    url = f"https://api.telegram.org/bot{token}/{method}"
    data = json.dumps(payload).encode() if payload is not None else None
    headers = {"Content-Type": "application/json"} if data else {}
    request = urllib.request.Request(url, data=data, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:400]
        raise SystemExit(f"Bot API error {exc.code}: {detail}") from exc


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--chat-id", type=int, help="set the button for one chat only")
    parser.add_argument("--clear", action="store_true", help="restore the command list button")
    parser.add_argument("--text", default="Файлы", help="button label")
    args = parser.parse_args()

    if args.clear:
        payload: dict = {"menu_button": {"type": "commands"}}
    else:
        url = _mini_app_url()
        if not url:
            raise SystemExit(
                "no public dashboard URL: set dashboard.public_url "
                "(hermes config set dashboard.public_url https://your-host)"
            )
        payload = {
            "menu_button": {"type": "web_app", "text": args.text, "web_app": {"url": url}}
        }
    if args.chat_id is not None:
        payload["chat_id"] = args.chat_id

    result = _call("setChatMenuButton", payload)
    print("ok:", result.get("ok"), "| button:", json.dumps(result.get("result"), ensure_ascii=False))

    check = _call("getChatMenuButton", {"chat_id": args.chat_id} if args.chat_id else {})
    print("now:", json.dumps(check.get("result"), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
