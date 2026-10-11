"""Shared sidebar navigation component."""

from __future__ import annotations

from typing import Any

from nicegui import ui

from dahlia.services.config import APP_VERSION


def _format_status_badge(is_online: bool) -> str:
    """Format connection status badge HTML."""
    if is_online:
        return '<span class="dahlia-status-badge dahlia-status-online">Online</span>'
    return '<span class="dahlia-status-badge dahlia-status-offline">Offline mode</span>'


def render_sidebar(controller: Any, active: str) -> None:
    """Render the left sidebar with brand, navigation and connection status.

    Parameters
    ----------
    controller:
        Application controller used for navigation callbacks.
    active:
        Key of the currently active screen.  Valid values: ``"setup"``,
        ``"my_results"``, ``"profile"``.  Login and register sub-screens
        pass ``"profile"`` to keep that item highlighted.
    """
    with ui.column().classes("dahlia-sidebar gap-0"):
        # Branding + connection status
        with ui.column().classes("dahlia-sidebar-top gap-1"):
            with ui.row().classes("items-baseline gap-2"):
                ui.label("DAHLIA").classes("dahlia-brand")
                ui.label(APP_VERSION).classes("dahlia-version")
            is_online = bool(getattr(controller, "is_online", False))
            status_badge = ui.html(_format_status_badge(is_online), sanitize=False)
            controller._status_badge = status_badge



        # Main navigation
        with ui.column().classes("dahlia-sidebar-nav gap-0"):
            _nav_item(
                icon="science",
                label="Experiment Setup",
                is_active=(active == "setup"),
                on_click=lambda: controller.show_setup(reset_defaults=False),
            )
            _nav_item(
                icon="bar_chart",
                label="My Results",
                is_active=(active == "my_results"),
                on_click=controller.show_my_results,
            )
            if controller.current_user and controller.current_user.get("role") == "DEVELOPER":
                _nav_item(
                    icon="admin_panel_settings",
                    label="Admin Panel",
                    is_active=(active == "admin"),
                    on_click=controller.show_admin,
                )

        # Profile
        with ui.column().classes("dahlia-sidebar-bottom gap-0"):
            _nav_item(
                icon="person",
                label="Profile",
                is_active=(active == "profile"),
                on_click=controller.show_profile,
            )


def _nav_item(
    icon: str,
    label: str,
    *,
    is_active: bool,
    on_click: Any,
) -> None:
    """Render a single sidebar navigation button with icon and label."""
    extra = "active" if is_active else ""
    with ui.button(on_click=on_click).props("flat no-caps").classes(
        f"dahlia-nav-item {extra}"
    ):
        ui.icon(icon)
        ui.label(label).classes("text-sm")
