"""Telegram Mini App API — managed-file access behind Telegram's signature.

The router lives here (package root) so it can use the package's relative
imports; ``dashboard/plugin_api.py`` loads this module for the dashboard's
plugin-API loader.

Auth: every route requires ``Authorization: Bearer <initData>``, where
``initData`` is Telegram's signed payload. The plugin's dashboard auth
provider verifies that signature against the bot token, so the request only
reaches this module when Telegram signed it. There is no session endpoint and
no second credential — the Telegram signature is the credential.

File access delegates to the dashboard's managed-files policy
(``hermes_cli.web_server_files``), so the same root lock and the same
credential denylist that guard the dashboard apply here — this module never
resolves a path on its own.
"""
from __future__ import annotations

import logging
import os
import secrets
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, Request

from .telegram_auth import parse_init_data, resolve_bot_token, verify_init_data

LOG = logging.getLogger("telegram-miniapp")

router = APIRouter()

_MAX_TEXT_BYTES = 512 * 1024
_MAX_WRITE_BYTES = 4 * 1024 * 1024
_MAX_ENTRIES = 2000


def _require_telegram_user(request: Request) -> str:
    """Verify the bearer token as Telegram-signed ``initData``; return the user id."""
    header = request.headers.get("authorization", "")
    parts = header.split(" ", 1)
    if len(parts) != 2 or parts[0].strip().lower() != "bearer":
        raise HTTPException(status_code=401, detail="Unauthorized")
    ok, user = verify_init_data(parts[1].strip(), bot_token=resolve_bot_token())
    if not ok:
        # The gate rejects the token before the route runs, so a failure here
        # means the client sent something the verifier could not accept. Log
        # WHY: an empty token, an expired payload and a bad signature are
        # three different bugs with three different fixes.
        LOG.warning(
            "telegram-miniapp: initData rejected: %s (token_len=%d, keys=%s)",
            user.get("error", "unknown"),
            len(parts[1].strip()),
            sorted(parse_init_data(parts[1].strip()).keys()),
        )
        raise HTTPException(status_code=401, detail="Unauthorized")
    user_id = str(user.get("id") or "")
    if not user_id:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return user_id


def _resolve(path: str, request: Request, *, for_write: bool = False):
    """Resolve a path through the dashboard's managed-files policy."""
    from hermes_cli.web_server_files import _resolve_managed_path

    return _resolve_managed_path(path, request, for_write=for_write)


def _is_sensitive(path: Path) -> bool:
    from hermes_cli.web_routers.files import _is_sensitive_path

    return _is_sensitive_path(path)


@router.get("/fs/list")
async def fs_list(request: Request, path: str = Query("")):
    """Directory listing inside the managed root."""
    _require_telegram_user(request)
    from hermes_cli.web_server_files import _managed_files_policy

    policy, target, display_path = _resolve(path, request)
    if not target.exists():
        raise HTTPException(status_code=404, detail="Path not found")
    if not target.is_dir():
        raise HTTPException(status_code=400, detail="Path is not a directory")
    entries = []
    try:
        with os.scandir(target) as scan:
            for entry in scan:
                if entry.name.startswith("."):
                    continue
                if _is_sensitive(Path(entry.path)):
                    continue
                try:
                    is_dir = entry.is_dir(follow_symlinks=False)
                except OSError:
                    continue
                entries.append(
                    {
                        "name": entry.name,
                        "path": str(Path(entry.path)),
                        "is_directory": is_dir,
                    }
                )
                if len(entries) >= _MAX_ENTRIES:
                    break
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"Could not read directory: {exc}")
    entries.sort(key=lambda item: (not item["is_directory"], item["name"].lower()))
    parent = None
    if target.parent != target:
        parent = str(target.parent)
    return {
        "path": display_path,
        "parent": parent,
        "entries": entries,
        "root": str(policy.locked_root) if policy.locked_root else None,
        "can_change_path": policy.can_change_path,
    }


@router.get("/fs/read")
async def fs_read(request: Request, path: str = Query(...)):
    """Read a text file (Markdown-first) inside the managed root."""
    _require_telegram_user(request)
    _, target, display_path = _resolve(path, request)
    if not target.exists():
        raise HTTPException(status_code=404, detail="File not found")
    if not target.is_file():
        raise HTTPException(status_code=400, detail="Path is not a file")
    if _is_sensitive(target):
        raise HTTPException(status_code=403, detail="Access to sensitive files is not allowed")
    size = target.stat().st_size
    if size > _MAX_TEXT_BYTES:
        raise HTTPException(status_code=413, detail="File is too large")
    data = target.read_bytes()
    if b"\x00" in data[:4096]:
        raise HTTPException(status_code=415, detail="Binary files are not supported")
    return {
        "path": display_path,
        "name": target.name,
        "byte_size": size,
        "text": data.decode("utf-8", errors="replace"),
        "is_markdown": target.suffix.lower() in {".md", ".markdown", ".mdx"},
    }


@router.post("/fs/write")
async def fs_write(request: Request):
    """Overwrite a text file atomically (staged temp file + rename)."""
    _require_telegram_user(request)
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001
        raise HTTPException(status_code=400, detail="Invalid JSON body")
    path = str((body or {}).get("path") or "")
    content = body.get("content")
    if not isinstance(content, str):
        raise HTTPException(status_code=400, detail="content must be a string")
    if len(content.encode("utf-8")) > _MAX_WRITE_BYTES:
        raise HTTPException(status_code=413, detail="Content is too large")
    if not path:
        raise HTTPException(status_code=400, detail="path is required")

    _, target, _ = _resolve(path, request, for_write=True)
    if target.exists() and not target.is_file():
        raise HTTPException(status_code=400, detail="Path points to a directory")
    if not target.parent.is_dir():
        raise HTTPException(status_code=400, detail="Parent directory does not exist")

    tmp = target.with_name(f".{target.name}.tgmini-{os.getpid()}-{secrets.token_hex(4)}")
    try:
        tmp.write_text(content, encoding="utf-8")
        os.replace(tmp, target)
    except OSError as exc:
        tmp.unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail=f"Could not write file: {exc}")
    return {"ok": True, "path": str(target), "byte_size": len(content.encode("utf-8"))}
