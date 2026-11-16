"""Telegram Mini App — a file browser and Markdown editor for the Hermes bot.

Surfaces:

* The Mini App page is served from this plugin's ``dashboard/`` directory and
  talks to the routes in ``dashboard/plugin_api.py``.
* The chat menu button opens it in one tap (``set_menu_button.py``); there is
  no bot command, so nothing has to be typed.

Auth model:

* The Mini App sends Telegram's signed ``initData`` as a bearer token.
* The plugin's dashboard auth provider verifies that signature against the
  bot token, so an unsigned or tampered payload is rejected at the gate.
* File access delegates to the dashboard's managed-files policy, so the same
  root lock and the same credential denylist that guard the dashboard apply
  here — this plugin never resolves a path on its own.
"""
from __future__ import annotations

import logging

LOG = logging.getLogger("telegram-miniapp")


def register(ctx) -> None:
    """Register the auth provider, the token routes and the Telegram handler."""
    from .telegram_bridge import register_bridge

    register_bridge(ctx)
    LOG.info("telegram-miniapp: registered")
