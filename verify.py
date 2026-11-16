"""Live check for the telegram-miniapp plugin: auth signature + provider.

Run from the Hermes checkout so the ``hermes_cli`` package is importable:
    python verify.py
"""
from __future__ import annotations

import hashlib
import hmac
import sys
import time
from pathlib import Path
from urllib.parse import urlencode

sys.path.insert(0, str(Path(__file__).resolve().parent))

from auth_provider import TelegramMiniAppProvider  # noqa: E402
from telegram_auth import resolve_bot_token, verify_init_data  # noqa: E402


def make_init_data(token: str, user_id: str = "123456789") -> str:
    """Build a correctly signed initData payload (Telegram's own algorithm).

    secret_key = HMAC_SHA256(bot_token, "WebAppData")
    hash = HMAC_SHA256(data_check_string, secret_key)
    """
    fields = {
        "auth_date": str(int(time.time())),
        "query_id": "AAH_test",
        "user": '{"id":"%s","first_name":"Test","username":"tester"}' % user_id,
    }
    check = "\n".join(f"{k}={fields[k]}" for k in sorted(fields))
    secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    fields["hash"] = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    return urlencode(fields)


def main() -> int:
    token = resolve_bot_token()
    assert token, "bot token not resolved"
    print("bot token resolved: len", len(token))

    # 1. valid payload
    payload = make_init_data(token)
    ok, user = verify_init_data(payload, bot_token=token)
    assert ok, f"valid payload rejected: {user}"
    assert user["id"] == "123456789", user
    print("valid initData accepted, user id:", user["id"])

    # 2. tampered payload
    tampered = payload.replace("Test", "Evil")
    ok, reason = verify_init_data(tampered, bot_token=token)
    assert not ok, "tampered payload accepted!"
    print("tampered initData rejected:", reason.get("error"))

    # 3. wrong bot token
    ok, reason = verify_init_data(payload, bot_token="wrong" + token)
    assert not ok, "payload accepted under a wrong bot token!"
    print("initData rejected under a wrong bot token")

    # 4. expired payload
    old = make_init_data(token)
    old_fields = dict(p.split("=", 1) for p in old.split("&"))
    old_fields["auth_date"] = str(int(time.time()) - 90000)
    old_check = "\n".join(f"{k}={old_fields[k]}" for k in sorted(old_fields) if k != "hash")
    old_fields["hash"] = hmac.new(
        hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest(),
        old_check.encode(),
        hashlib.sha256,
    ).hexdigest()
    ok, reason = verify_init_data(urlencode(old_fields), bot_token=token)
    assert not ok, "expired payload accepted!"
    print("expired initData rejected:", reason.get("error"))

    # 5. the provider accepts the valid payload and rejects everything else
    provider = TelegramMiniAppProvider()
    principal = provider.verify_token(token=payload)
    assert principal is not None, "provider rejected a valid payload"
    assert principal.principal == "telegram:123456789", principal
    print("provider principal:", principal.principal)

    assert provider.verify_token(token=tampered) is None, "provider accepted tampering!"
    assert provider.verify_token(token="") is None, "provider accepted an empty token"
    print("provider rejects tampered/empty tokens")

    # 6. the OLD signing scheme must be rejected: it proves the verifier is
    #    actually checking Telegram's current HMAC scheme and not accepting
    #    any self-consistent payload.
    legacy_fields = {
        "auth_date": str(int(time.time())),
        "query_id": "AAH_test",
        "user": '{"id":"%s","first_name":"Test"}' % "123456789",
    }
    legacy_check = "\n".join(f"{k}={legacy_fields[k]}" for k in sorted(legacy_fields))
    legacy_fields["hash"] = hmac.new(
        hashlib.sha256(token.encode()).digest(), legacy_check.encode(), hashlib.sha256
    ).hexdigest()
    ok, reason = verify_init_data(urlencode(legacy_fields), bot_token=token)
    assert not ok, "the legacy SHA256(bot_token) scheme was accepted!"
    print("legacy signing scheme rejected:", reason.get("error"))

    # 7. Telegram's third-party ``signature`` field IS part of the data check
    #    string (Telegram's own init-data-node ``validate()`` skips ``hash``
    #    only). A payload signed WITH the signature field must validate, and
    #    the same payload signed WITHOUT it must not.
    signed_fields = {
        "auth_date": str(int(time.time())),
        "query_id": "AAH_test",
        "user": '{"id":"%s","first_name":"Test"}' % "123456789",
        "signature": "AAH_not_a_real_ed25519_signature",
    }
    signed_check = "\n".join(f"{k}={signed_fields[k]}" for k in sorted(signed_fields))
    signed_fields["hash"] = hmac.new(
        hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest(),
        signed_check.encode(),
        hashlib.sha256,
    ).hexdigest()
    ok, user = verify_init_data(urlencode(signed_fields), bot_token=token)
    assert ok, f"payload with a signature field rejected: {user}"
    print("payload carrying a signature field accepted")

    # The same fields signed while EXCLUDING ``signature`` must be rejected:
    # that proves the field is part of the signed string.
    without_sig = dict(signed_fields)
    without_sig.pop("signature")
    without_check = "\n".join(f"{k}={without_sig[k]}" for k in sorted(without_sig))
    without_sig["hash"] = hmac.new(
        hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest(),
        without_check.encode(),
        hashlib.sha256,
    ).hexdigest()
    ok, reason = verify_init_data(urlencode(without_sig), bot_token=token)
    assert not ok, "a payload signed without the signature field was accepted!"
    print("payload signed without the signature field rejected:", reason.get("error"))

    # 8. the HMAC key/message order matters: Telegram computes
    #    HMAC(key="WebAppData", message=bot_token). The swapped variant must
    #    be rejected.
    swapped_fields = {
        "auth_date": str(int(time.time())),
        "query_id": "AAH_test",
        "user": '{"id":"%s","first_name":"Test"}' % "123456789",
    }
    swapped_check = "\n".join(f"{k}={swapped_fields[k]}" for k in sorted(swapped_fields))
    swapped_fields["hash"] = hmac.new(
        hmac.new(token.encode(), b"WebAppData", hashlib.sha256).digest(),
        swapped_check.encode(),
        hashlib.sha256,
    ).hexdigest()
    ok, reason = verify_init_data(urlencode(swapped_fields), bot_token=token)
    assert not ok, "the swapped HMAC key/message order was accepted!"
    print("swapped HMAC key/message order rejected:", reason.get("error"))

    print("\nOK: all telegram-miniapp auth checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
