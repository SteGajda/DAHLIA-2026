"""Shared compact DAHLIA branding."""

from nicegui import ui

from dahlia.services.config import APP_VERSION


def brand() -> None:
    """Render the compact DAHLIA brand mark (name + version badge)."""
    with ui.row().classes("items-baseline gap-2"):
        ui.label("DAHLIA").classes("dahlia-brand")
        ui.label(APP_VERSION).classes("dahlia-version")
