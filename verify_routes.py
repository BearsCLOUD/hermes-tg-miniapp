"""Live check: the plugin's routes mount and the FS behaviour is real.

Runs the dashboard's plugin-API loader, then drives the router with a real
Telegram-signed bearer through FastAPI's TestClient:

* no token            -> 401
* tampered token      -> 401
* valid token         -> list / read / write against a scratch dir
* path outside root   -> 403
* a .env file         -> not listed, not readable
"""
from __future__ import annotations

import hashlib
import hmac
import os
import sys
import tempfile
import time
from pathlib import Path
from urllib.parse import urlencode

_HERE = Path(__file__).resolve().parent

SCRATCH = Path(tempfile.gettempdir()) / "tgmini-verify"
SCRATCH.mkdir(parents=True, exist_ok=True)
(SCRATCH / "notes.md").write_text("# Заметки\n\nисходный текст\n", encoding="utf-8")
(SCRATCH / ".env").write_text("SECRET=must-not-leak\n", encoding="utf-8")
(SCRATCH / "subdir").mkdir(exist_ok=True)
(SCRATCH / "subdir" / "nested.md").write_text("nested\n", encoding="utf-8")

sys.path.insert(0, str(_HERE))

from telegram_auth import resolve_bot_token  # noqa: E402


def make_init_data(token: str, user_id: str = "123456789") -> str:
    fields = {
        "auth_date": str(int(time.time())),
        "user": '{"id":"%s","first_name":"Test"}' % user_id,
    }
    check = "\n".join(f"{k}={fields[k]}" for k in sorted(fields))
    secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    fields["hash"] = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    return urlencode(fields)


def main() -> int:
    os.environ.setdefault("HERMES_HOME", os.path.expanduser("~/.hermes"))
    os.environ["HERMES_DASHBOARD_FILES_ROOT"] = str(SCRATCH)

    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    # Import the plugin's API module. The package directory may be named
    # either after the plugin ("telegram-miniapp") or after the repository
    # ("hermes-tg-miniapp"), so load it by path instead of by name.
    import importlib.util

    module_name = "telegram_miniapp_api_for_check"
    spec = importlib.util.spec_from_file_location(
        module_name, _HERE / "api.py", submodule_search_locations=[str(_HERE)]
    )
    api_module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = api_module
    spec.loader.exec_module(api_module)

    app = FastAPI()
    app.include_router(api_module.router, prefix="/api/plugins/telegram-miniapp")
    client = TestClient(app)

    token = resolve_bot_token()
    valid = make_init_data(token)
    auth = {"Authorization": f"Bearer {valid}"}

    # 1. no token -> 401
    resp = client.get("/api/plugins/telegram-miniapp/fs/list")
    assert resp.status_code == 401, resp.status_code
    print("no token ->", resp.status_code)

    # 2. tampered token -> 401
    resp = client.get(
        "/api/plugins/telegram-miniapp/fs/list",
        headers={"Authorization": f"Bearer {valid.replace('Test', 'Evil')}"},
    )
    assert resp.status_code == 401, resp.status_code
    print("tampered token ->", resp.status_code)

    # 3. valid token -> listing
    resp = client.get("/api/plugins/telegram-miniapp/fs/list", headers=auth)
    assert resp.status_code == 200, (resp.status_code, resp.text)
    data = resp.json()
    names = sorted(e["name"] for e in data["entries"])
    print("listing:", names)
    assert "notes.md" in names, names
    assert ".env" not in names, "denylisted .env was listed!"
    assert data["root"] == str(SCRATCH), data["root"]
    print("root locked to:", data["root"])

    # 4. read a markdown file
    resp = client.get(
        "/api/plugins/telegram-miniapp/fs/read",
        params={"path": str(SCRATCH / "notes.md")},
        headers=auth,
    )
    assert resp.status_code == 200, (resp.status_code, resp.text)
    body = resp.json()
    assert body["is_markdown"] is True, body
    assert "исходный текст" in body["text"], body
    print("read notes.md ->", body["byte_size"], "bytes, markdown:", body["is_markdown"])

    # 5. reading .env is refused
    resp = client.get(
        "/api/plugins/telegram-miniapp/fs/read",
        params={"path": str(SCRATCH / ".env")},
        headers=auth,
    )
    assert resp.status_code == 403, (resp.status_code, resp.text)
    print("read .env ->", resp.status_code)

    # 6. write the file
    resp = client.post(
        "/api/plugins/telegram-miniapp/fs/write",
        json={"path": str(SCRATCH / "notes.md"), "content": "# Заметки\n\nизменено\n"},
        headers=auth,
    )
    assert resp.status_code == 200, (resp.status_code, resp.text)
    saved = (SCRATCH / "notes.md").read_text(encoding="utf-8")
    assert "изменено" in saved, saved
    print("write notes.md -> ok, content:", saved.strip().replace("\n", " | "))

    # 7. path outside the root -> 403
    resp = client.get(
        "/api/plugins/telegram-miniapp/fs/read",
        params={"path": "/etc/hostname"},
        headers=auth,
    )
    assert resp.status_code in (403, 404), (resp.status_code, resp.text)
    print("read outside root ->", resp.status_code)

    # 8. traversal attempt -> refused
    resp = client.get(
        "/api/plugins/telegram-miniapp/fs/read",
        params={"path": str(SCRATCH / ".." / ".." / "etc" / "hostname")},
        headers=auth,
    )
    assert resp.status_code in (400, 403, 404), (resp.status_code, resp.text)
    print("traversal attempt ->", resp.status_code)

    print("\nOK: all telegram-miniapp route checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
