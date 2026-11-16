"""Token-only dashboard auth provider for the Telegram Mini App.

The Mini App's bearer token IS Telegram's signed ``initData``. This provider
verifies that signature against the bot token (HMAC-SHA256, per Telegram's
Mini App specification), so a tampered or forged payload never reaches the
plugin's routes — the dashboard's token-auth seam rejects it at the gate.

Non-interactive by construction: it never mints a cookie session, so it is
never offered on the login page.
"""
from __future__ import annotations

import logging
from typing import Optional

from hermes_cli.dashboard_auth import DashboardAuthProvider, Session, TokenPrincipal

try:  # imported as a package submodule (the normal plugin loading path)
    from .telegram_auth import parse_init_data, resolve_bot_token, verify_init_data
except ImportError:  # imported as a top-level module (standalone scripts)
    from telegram_auth import parse_init_data, resolve_bot_token, verify_init_data

LOG = logging.getLogger("telegram-miniapp")


class TelegramMiniAppProvider(DashboardAuthProvider):
    """Verifies Telegram ``initData``; principal is the Telegram user id."""

    name = "telegram-miniapp"
    display_name = "Telegram Mini App"
    supports_token = True
    supports_session = False

    def verify_token(self, *, token: str) -> Optional[TokenPrincipal]:
        ok, user = verify_init_data(token, bot_token=resolve_bot_token())
        if not ok:
            # The gate logs only "no provider recognised this token", which
            # hides the actual reason. An empty token, an expired payload and
            # a bad signature are three different bugs; record which one.
            # The client IP is on the gate's own audit line for the same
            # request, so this entry only needs the payload shape.
            LOG.warning(
                "telegram-miniapp: initData rejected: %s (token_len=%d, keys=%s)",
                user.get("error", "unknown"),
                len(token or ""),
                sorted(parse_init_data(token or "").keys()),
            )
            return None
        user_id = str(user.get("id") or "")
        if not user_id:
            return None
        principal = f"telegram:{user_id}"
        # The gate logs only failures, so a request that reaches us with a
        # valid signature leaves no trace. That makes "the phone never
        # arrived" and "the phone arrived and was accepted" look identical.
        # Record the acceptance (never the payload) so the next outage can be
        # told apart from the next one.
        LOG.info(
            "telegram-miniapp: initData accepted (principal=%s, token_len=%d)",
            principal,
            len(token or ""),
        )
        return TokenPrincipal(
            principal=principal, provider=self.name, scopes=("miniapp",)
        )

    # --- interactive methods: unsupported (token-only) ---

    def verify_session(self, *, access_token: str) -> Optional[Session]:
        return None

    def refresh_session(self, *, refresh_token: str) -> Session:
        raise NotImplementedError("telegram-miniapp is token-only")

    def revoke_session(self, *, refresh_token: str) -> None:
        return None

    def start_login(self, *, redirect_uri: str):
        raise NotImplementedError("telegram-miniapp has no login flow")

    def complete_login(
        self, *, code: str, state: str, code_verifier: str, redirect_uri: str
    ) -> Session:
        raise NotImplementedError("telegram-miniapp has no login flow")
