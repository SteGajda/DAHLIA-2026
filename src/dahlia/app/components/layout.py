"""Shared page layout helpers."""

from __future__ import annotations

from typing import Any

from nicegui import ui

from dahlia.app.components.sidebar import render_sidebar


def sidebar_page(
    controller: Any,
    active: str,
    page_title: str | None = None,
) -> ui.column:
    """Build the standard sidebar layout and return the content column.

    Creates a full-height flex row: the sidebar on the left and an empty
    content column on the right.  An optional thin header bar with
    *page_title* is prepended to the content column when provided.

    Callers should use the returned element as a context manager to add their
    screen-specific content::

        with sidebar_page(controller, "setup"):
            with ui.element("main").classes("dahlia-setup-main"):
                ...

    Parameters
    ----------
    controller:
        Application controller.
    active:
        Active screen key forwarded to the sidebar for highlighting.
    page_title:
        Optional title shown in the thin breadcrumb header bar inside the
        content column.  Pass ``None`` to omit the header entirely.
    """
    row = ui.row().classes("dahlia-page-row gap-0")
    with row:
        render_sidebar(controller, active)
        with ui.column().classes("dahlia-content-page gap-0") as content:
            if page_title is not None:
                with ui.row().classes("dahlia-content-header"):
                    ui.label(page_title).classes("text-sm dahlia-muted")
    return content
