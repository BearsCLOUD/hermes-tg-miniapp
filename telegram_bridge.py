"""Telegram-side bridge for the Mini App.

Registers:

* the plugin's token routes with the dashboard's token-auth seam, so the
  interactive OAuth gate lets the plugin's API through — the same mechanism
  the ``drain`` plugin uses; and
* the dashboard auth provider that verifies Telegram's signed ``initData``.

The Mini App is opened by a **button**, not by a command: the chat menu
button carries a ``web_app`` payload, so the app opens in one tap and the
user never types anything. A command would only add a second way to reach
the same page, and it would compete with the built-in command handling.
"""
from __future__ import annotations

import logging
import os

LOG = logging.getLogger("telegram-miniapp")

# API routes owned by this plugin (mounted under /api/plugins/telegram-miniapp/).
API_ROUTES = (
    "/api/plugins/telegram-miniapp/fs/list",
    "/api/plugins/telegram-miniapp/fs/read",
    "/api/plugins/telegram-miniapp/fs/write",
)

MINI_APP_PATH = "/dashboard-plugins/telegram-miniapp/index.html"


def _mini_app_url() -> str:
    """Public HTTPS URL of the Mini App page.

    The dashboard's ``dashboard.public_url`` / ``HERMES_DASHBOARD_PUBLIC_URL``
    is the operator-declared external URL; Telegram requires HTTPS, so a
    missing public URL means the button cannot be built.
    """
    raw = os.environ.get("HERMES_DASHBOARD_PUBLIC_URL", "").strip()
    if not raw:
        try:
            from hermes_cli.dashboard_auth.prefix import resolve_public_url

            raw = (resolve_public_url() or "").strip()
        except Exception:  # noqa: BLE001 — a missing URL must not break the bot
            raw = ""
    if not raw:
        return ""
    return raw.rstrip("/") + MINI_APP_PATH


def register_bridge(ctx) -> None:
    """Register the auth provider and the token routes."""
    from .auth_provider import TelegramMiniAppProvider

    from hermes_cli.dashboard_auth.token_auth import register_token_route

    for route in API_ROUTES:
        register_token_route(route)

    ctx.register_dashboard_auth_provider(TelegramMiniAppProvider())
    LOG.info("telegram-miniapp: registered token routes and auth provider")
