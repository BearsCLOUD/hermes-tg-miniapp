"""Dashboard plugin API entry point.

The dashboard's plugin loader imports this file standalone (it is not part of
the plugin package), so relative imports would fail here. It loads the
package's ``api`` module with the package directory as its search path, which
keeps the router's own relative imports working, and re-exports ``router``.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_PLUGIN_ROOT = Path(__file__).resolve().parent.parent
_MODULE_NAME = "telegram_miniapp_dashboard_api"


def _load_api_module():
    """Import the plugin package's ``api`` module with relative imports intact."""
    if _MODULE_NAME in sys.modules:
        return sys.modules[_MODULE_NAME]
    spec = importlib.util.spec_from_file_location(
        _MODULE_NAME,
        _PLUGIN_ROOT / "api.py",
        submodule_search_locations=[str(_PLUGIN_ROOT)],
    )
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load telegram-miniapp api module from {_PLUGIN_ROOT}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[_MODULE_NAME] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        sys.modules.pop(_MODULE_NAME, None)
        raise
    return module


router = _load_api_module().router
