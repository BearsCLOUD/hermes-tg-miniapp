"""Telegram Mini App ``initData`` validation.

Telegram signs the raw query string of ``Telegram.WebApp.initData`` with an
HMAC-SHA256. The secret key is ``HMAC_SHA256(<bot_token>, "WebAppData")`` and the
data check string is the sorted ``key=value`` pairs joined by ``\\n``, excluding
the ``hash`` field only — the third-party ``signature`` field is part of it.

Reference: Telegram Mini Apps — Validating data received via the Mini App, and
Telegram's own ``@telegram-apps/init-data-node`` implementation.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import time
from typing import Any
from urllib.parse import parse_qsl

# Telegram's own guidance: reject data older than a day.
MAX_AGE_SECONDS = 24 * 60 * 60


def resolve_bot_token() -> str:
    """Resolve the bot token the same way the Telegram adapter does."""
    try:
        from hermes_cli.config import get_env_value_prefer_dotenv

        token = get_env_value_prefer_dotenv("TELEGRAM_BOT_TOKEN") or ""
    except Exception:  # noqa: BLE001 — config reader must not break the plugin
        token = ""
    return token.strip()


def _secret_key(token: str) -> bytes:
    """``HMAC_SHA256(<bot_token>, "WebAppData")`` — Telegram's current scheme.

    Telegram's own ``init-data-node`` library computes it as
    ``createHmac("sha256", key="WebAppData").update(bot_token)``: the
    constant is the HMAC *key* and the bot token is the *message*. Swapping
    the two yields a different digest, so the order matters.
    """
    return hmac.new(b"WebAppData", token.encode("utf-8"), hashlib.sha256).digest()


def parse_init_data(init_data: str) -> dict[str, str]:
    """Parse the raw query string into a dict (last value wins)."""
    if not init_data or not isinstance(init_data, str):
        return {}
    return {key: value for key, value in parse_qsl(init_data, keep_blank_values=True)}


def verify_init_data(
    init_data: str,
    *,
    bot_token: str,
    max_age_seconds: int = MAX_AGE_SECONDS,
    now: float | None = None,
) -> tuple[bool, dict[str, Any]]:
    """Validate Telegram's signature over ``initData``.

    Returns ``(ok, user)`` where ``user`` carries the verified fields
    (``id``, ``first_name``, ``username``, ``auth_date``) on success and the
    failure reason on failure. Never raises for attacker-controlled input.
    """
    if not bot_token:
        return False, {"error": "bot token not configured"}
    fields = parse_init_data(init_data)
    if not fields:
        return False, {"error": "empty init data"}
    received_hash = fields.pop("hash", "")
    if not received_hash:
        return False, {"error": "missing hash"}
    # Only ``hash`` is excluded from the data check string. The third-party
    # ``signature`` field IS part of it (Telegram's own init-data-node
    # library: ``validate()`` skips ``hash`` only, while ``validate3rd()``
    # skips both because it signs a different string).

    data_check_string = "\n".join(
        f"{key}={value}" for key, value in sorted(fields.items())
    )
    expected = hmac.new(
        _secret_key(bot_token), data_check_string.encode("utf-8"), hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(expected, received_hash):
        return False, {"error": "bad signature"}

    try:
        auth_date = int(fields.get("auth_date", ""))
    except (TypeError, ValueError):
        return False, {"error": "missing auth_date"}
    current = time.time() if now is None else now
    if auth_date > current + 60:
        return False, {"error": "auth_date in the future"}
    if current - auth_date > max_age_seconds:
        return False, {"error": "init data expired"}

    user: dict[str, Any] = {
        "id": fields.get("id", ""),
        "first_name": fields.get("first_name", ""),
        "username": fields.get("username", ""),
        "auth_date": auth_date,
    }
    # Telegram sends the user as a JSON string in the ``user`` field; the
    # top-level convenience fields are not always present.
    raw_user = fields.get("user", "")
    if raw_user:
        try:
            parsed = json.loads(raw_user)
        except (TypeError, ValueError):
            parsed = None
        if isinstance(parsed, dict):
            user["id"] = str(parsed.get("id", user["id"]) or "")
            user["first_name"] = str(parsed.get("first_name", "") or "")
            user["username"] = str(parsed.get("username", "") or "")
    return True, user
