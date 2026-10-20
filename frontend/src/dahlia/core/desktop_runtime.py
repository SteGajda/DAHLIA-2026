"""Stdlib-only bootstrap for the frozen Windows executable."""

from __future__ import annotations

import json
import os
from pathlib import Path
import sys


def configure_desktop_runtime() -> None:
    """Load packaged defaults without reading .env files or backend secrets."""
    if not getattr(sys, "frozen", False):
        return
    state = Path(os.environ.get("APPDATA", str(Path.home()))) / "DAHLIA"
    logs = state / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    # --windowed removes the streams required by Uvicorn and tracebacks.
    for name in ("stdout", "stderr"):
        if getattr(sys, name) is None:
            setattr(sys, name, (logs / "desktop.log").open("a", encoding="utf-8", buffering=1))
    config = json.loads((Path(sys._MEIPASS) / "dahlia_build.json").read_text(encoding="utf-8"))
    os.environ.setdefault("DAHLIA_API_URL", str(config["api_url"]))
    os.environ.setdefault("DAHLIA_API_TIMEOUT", str(config["api_timeout"]))


def report_startup_error() -> None:
    """Make a windowed startup failure visible without displaying secrets."""
    import traceback
    traceback.print_exc()
    if getattr(sys, "frozen", False) and sys.platform == "win32":
        import ctypes
        ctypes.windll.user32.MessageBoxW(
            None,
            "DAHLIA could not start. See %APPDATA%\\DAHLIA\\logs\\desktop.log. "
            "Check that Microsoft Edge WebView2 Runtime is installed.",
            "DAHLIA startup error", 0x10,
        )
