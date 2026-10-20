"""Native desktop entry point for DAHLIA 1.1."""

from __future__ import annotations

import os
import sys
from multiprocessing import freeze_support
from typing import Any

from nicegui import app, native as native_window, ui

from dahlia.app.controller import AppController
from dahlia.app.theme import APP_CSS, ESCAPE_AND_EXIT_GUARD
from dahlia.services.config import APP_VERSION

# Native-window configuration must be outside the main guard because NiceGUI
# launches the window in a separate process.
app.native.window_args["resizable"] = False


def root() -> None:
    ui.colors(
        primary="#6B5DD3",
        secondary="#777780",
        accent="#6B5DD3",
        positive="#25845d",
        negative="#c93f4b",
    )
    ui.add_css(APP_CSS)
    ui.add_head_html(ESCAPE_AND_EXIT_GUARD)
    root_container = ui.column().classes("dahlia-root gap-0")
    controller = AppController(root_container)
    controller.show_setup(reset_defaults=True)


def main(*, native: bool | None = None, port: int | None = None) -> None:
    freeze_support()
    is_native = (
        native
        if native is not None
        else ("--browser" not in sys.argv and os.getenv("DAHLIA_NATIVE", "1") == "1")
    )
    # NiceGUI internal webview must not use port 8000 (reserved for backend API)
    if port is None and not os.getenv("DAHLIA_PORT") and getattr(sys, "frozen", False):
        app_port = native_window.find_open_port()
    else:
        app_port = port or int(os.getenv("DAHLIA_PORT", "8080") or "8080")
    run_kwargs: dict[str, Any] = {
        "title": f"DAHLIA {APP_VERSION}",
        "native": is_native,
        "dark": False,
        "language": "en-US",
        "reload": False,
        "show": False,
        "show_welcome_message": False,
        "port": app_port,
    }
    if getattr(sys, "frozen", False):
        run_kwargs["host"] = "127.0.0.1"
    if is_native:
        run_kwargs["fullscreen"] = True

    ui.run(root=root, **run_kwargs)


if __name__ == "__main__":
    main()

