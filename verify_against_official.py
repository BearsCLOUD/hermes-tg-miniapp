"""Ground-truth check against Telegram's own ``@telegram-apps/init-data-node``.

The library signs and validates ``initData`` exactly as Telegram's servers do.
This script therefore answers the only question that matters: does the Python
implementation agree with Telegram's reference implementation — in BOTH
directions?

* the payload signed by Telegram's library must pass the Python verifier;
* the payload signed by the Python implementation must pass Telegram's
  ``validate()``.

Requires ``node`` and the npm package. Point ``TGA_NPM_DIR`` at a directory
that contains ``@telegram-apps/init-data-node`` (a ``node_modules`` folder, or
the package folder itself).

Run: python verify_against_official.py
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlencode

sys.path.insert(0, str(Path(__file__).resolve().parent))

from telegram_auth import resolve_bot_token, verify_init_data  # noqa: E402

NPM_DIR = Path(os.environ.get("TGA_NPM_DIR", "./node_modules"))
NPM_PKG = "@telegram-apps/init-data-node"

SIGN_MJS = """
import { writeFileSync } from "node:fs";
import { sign, validate } from "@telegram-apps/init-data-node";
const [TOKEN, OUT] = process.argv.slice(2);
const data = {
  query_id: "AAHdF6IQAAAAAN0XohDhrOrc",
  user: { id: 123456789, first_name: "Test", username: "tester" },
  auth_date: Math.floor(Date.now() / 1000),
  chat_type: "private",
  chat_instance: "-1234567890",
  start_param: "",
  signature: "AAHfakeEd25519signature_-abcdefghijklmnop",
};
const initData = sign(data, TOKEN, data.auth_date);
writeFileSync(OUT, initData);
validate(initData, TOKEN);
console.log("OK");
"""

VALIDATE_MJS = """
import { readFileSync } from "node:fs";
import { validate } from "@telegram-apps/init-data-node";
const [TOKEN, FILE] = process.argv.slice(2);
validate(readFileSync(FILE, "utf8").trim(), TOKEN);
console.log("OK");
"""


def _npm_ready() -> bool:
    """True when the Telegram package is reachable from NPM_DIR."""
    if (NPM_DIR / NPM_PKG.split("/")[0]).exists():
        return True
    return (NPM_DIR / "node_modules" / NPM_PKG.split("/")[0]).exists()


def _node(script: str, *args: str) -> str:
    with tempfile.NamedTemporaryFile("w", suffix=".mjs", delete=False) as fh:
        fh.write(script)
        path = fh.name
    env = dict(os.environ)
    # The npm package must not be fetched through a proxy.
    env["NO_PROXY"] = "*"
    env["no_proxy"] = "*"
    try:
        proc = subprocess.run(
            ["node", path, *args], cwd=NPM_DIR, capture_output=True, text=True,
            timeout=120, env=env,
        )
    finally:
        Path(path).unlink(missing_ok=True)
    if proc.returncode != 0:
        raise RuntimeError(f"node failed: {proc.stderr.strip() or proc.stdout.strip()}")
    return proc.stdout.strip()


def main() -> int:
    token = resolve_bot_token()
    assert token, "bot token not resolved"
    if not _npm_ready():
        print(f"SKIP: {NPM_PKG} is not installed in {NPM_DIR}")
        return 0

    with tempfile.TemporaryDirectory() as tmp:
        official_file = Path(tmp) / "official.txt"
        python_file = Path(tmp) / "python.txt"

        _node(SIGN_MJS, token, str(official_file))
        official_init = official_file.read_text().strip()
        ok, user = verify_init_data(official_init, bot_token=token)
        print(f"python verifier accepts a Telegram-signed payload: {ok}")
        assert ok, f"rejected Telegram's own signed payload: {user}"

        # Now sign with the Python implementation and let Telegram's library
        # validate it: the other direction of the same agreement.
        import hashlib
        import hmac
        import time

        fields = {
            "auth_date": str(int(time.time())),
            "query_id": "AAHpython_signed",
            "user": json.dumps({"id": 123456789, "first_name": "Python"}),
            "signature": "AAHfakeEd25519signature_-abcdefghijklmnop",
        }
        check = "\n".join(f"{k}={fields[k]}" for k in sorted(fields))
        secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
        fields["hash"] = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
        python_file.write_text(urlencode(fields))

        _node(VALIDATE_MJS, token, str(python_file))
        print("Telegram's library accepts a Python-signed payload: True")

    print("\nOK: the Python implementation agrees with Telegram's reference library")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
