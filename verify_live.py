"""Live end-to-end check against a running Hermes dashboard.

Signs a request the way Telegram does, sends it to the live Mini App API,
and checks that a valid payload is accepted while a tampered one, one signed
with the wrong bot token, and an anonymous request are all rejected.

Needs a reachable dashboard: set ``MINIAPP_API`` to the API base (default:
the public Hermes host) and ``MINIAPP_BOT_TOKEN`` if the bot token is not in
the environment.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import sys
import time
import urllib.error
import urllib.request
from urllib.parse import urlencode

API = os.environ.get(
    "MINIAPP_API", "https://hermes.bears.ru/api/plugins/telegram-miniapp"
).rstrip("/")


def resolve_bot_token() -> str:
    explicit = os.environ.get("MINIAPP_BOT_TOKEN", "").strip()
    if explicit:
        return explicit
    try:
        from hermes_cli.config import get_env_value_prefer_dotenv

        return (get_env_value_prefer_dotenv("TELEGRAM_BOT_TOKEN") or "").strip()
    except Exception:  # noqa: BLE001 — the check reports this itself
        return ""


def make_init_data(token: str, user_id: str = "123456789") -> str:
    """Sign a payload exactly as Telegram does (HMAC-SHA256 over sorted pairs)."""
    fields = {
        "auth_date": str(int(time.time())),
        "query_id": "AAH_live_check",
        "user": json.dumps({"id": user_id, "first_name": "Live", "username": "live"}),
    }
    check = "\n".join(f"{k}={fields[k]}" for k in sorted(fields))
    secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    fields["hash"] = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    return urlencode(fields)


def call(path: str, bearer: str | None) -> tuple[int, str]:
    req = urllib.request.Request(API + path, method="GET")
    if bearer:
        req.add_header("Authorization", f"Bearer {bearer}")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", "replace")
    except urllib.error.URLError as exc:
        print(f"cannot reach {API}: {exc.reason}")
        raise SystemExit(1) from exc


def main() -> int:
    token = resolve_bot_token()
    if not token:
        print("no bot token: set TELEGRAM_BOT_TOKEN or MINIAPP_BOT_TOKEN")
        return 1

    failures = 0

    status, body = call("/fs/list", make_init_data(token))
    if status == 200:
        try:
            entries = len(json.loads(body).get("entries", []))
            print(f"fs/list with a valid signature -> {status}, {entries} entries")
        except ValueError:
            print(f"fs/list with a valid signature -> {status}, unreadable body")
            failures += 1
    else:
        print(f"fs/list with a valid signature -> {status}: {body[:120]}")
        failures += 1

    tampered = make_init_data(token).replace("query_id=AAH", "query_id=XXX")
    status, _ = call("/fs/list", tampered)
    print(f"fs/list with a tampered payload -> {status}")
    if status != 401:
        failures += 1

    status, _ = call("/fs/list", make_init_data("0000000000:wrong-token-value-for-the-check"))
    print(f"fs/list signed with a wrong bot token -> {status}")
    if status != 401:
        failures += 1

    status, _ = call("/fs/list", None)
    print(f"fs/list without a token -> {status}")
    if status != 401:
        failures += 1

    print()
    if failures:
        print(f"FAILED: {failures} check(s) did not hold")
        return 1
    print("OK: live end-to-end check passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
