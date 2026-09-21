"""Native desktop entry point for DAHLIA 1.1."""

from __future__ import annotations

from multiprocessing import freeze_support

from nicegui import app, ui

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


def main() -> None:
    freeze_support()
    ui.run(
        root=root,
        title=f"DAHLIA {APP_VERSION}",
        native=True,
        fullscreen=True,
        dark=False,
        language="en-US",
        reload=False,
        show=False,
        show_welcome_message=False,
    )


if __name__ == "__main__":
    main()
