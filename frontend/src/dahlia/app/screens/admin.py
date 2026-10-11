"""Admin Panel screen for DEVELOPER role."""

from __future__ import annotations

from typing import Any

from nicegui import ui

from dahlia.app.components.layout import sidebar_page

_COLUMNS: list[tuple[str, str]] = [
    ("REQ ID", "90px"),
    ("USER ID", "100px"),
    ("REQUESTED ROLE", "160px"),
    ("SUBMITTED AT", "180px"),
    ("ACTIONS", "170px"),
]

_ROLE_BADGES: dict[str, tuple[str, str]] = {
    "USER_PLUS": ("User+", "#fff0dc", "#8a5700"),
    "RESEARCHER": ("Researcher", "#d4f7e8", "#1a7a4a"),
}


def render_admin(controller: Any) -> None:
    """Render the Admin Panel for users with DEVELOPER role."""
    with sidebar_page(controller, "admin", "Admin Panel"):
        with ui.element("main").classes("dahlia-content-main"):
            ui.label("Admin Panel").classes("dahlia-title")
            ui.label(
                "Review and manage user role upgrade requests. "
                "Approving a request immediately promotes the user in the database."
            ).classes("text-sm dahlia-muted mb-5")

            # Actions row
            with ui.row().classes("items-center justify-between gap-2 mb-4"):
                ui.label("Pending Requests").classes("text-base font-semibold")
                refresh_btn = ui.button(
                    "Refresh",
                    icon="refresh",
                ).props("flat no-caps dense").classes("text-sm")

            # Container for table / empty states
            table_container = ui.column().classes("w-full gap-0")

            async def load_requests() -> None:
                table_container.clear()
                with table_container:
                    with ui.row().classes("items-center gap-2 py-8"):
                        ui.spinner(size="sm")
                        ui.label("Loading requests from server...").classes(
                            "text-sm dahlia-muted"
                        )

                res = await controller.api_client.list_role_requests()
                table_container.clear()

                with table_container:
                    if res.is_offline:
                        _render_offline_state()
                        return

                    if not res.success:
                        _render_error_state(res.error or "Could not fetch requests.")
                        return

                    requests = res.data or []
                    if not requests:
                        _render_empty_state()
                    else:
                        _render_table(controller, requests, on_action=load_requests)

            refresh_btn.on_click(load_requests)
            ui.timer(0.01, load_requests, once=True)


def _render_empty_state() -> None:
    """Render state when there are no pending requests."""
    with ui.column().classes("items-center w-full py-16 gap-3"):
        ui.icon("check_circle").classes("text-5xl text-emerald-600")
        ui.label("No pending role requests.").classes("text-base font-medium")
        ui.label(
            "All submitted user requests have been processed."
        ).classes("text-sm dahlia-muted")


def _render_offline_state() -> None:
    """Render state when backend is unreachable."""
    with ui.column().classes("items-center w-full py-16 gap-3"):
        ui.icon("cloud_off").classes("text-5xl dahlia-muted")
        ui.label("Offline mode").classes("text-base font-medium")
        ui.label(
            "Cannot connect to the server to manage role requests."
        ).classes("text-sm dahlia-muted")


def _render_error_state(error_message: str) -> None:
    """Render state when API returns an error."""
    with ui.column().classes("items-center w-full py-16 gap-3"):
        ui.icon("error_outline").classes("text-5xl text-red-600")
        ui.label("Failed to load requests").classes("text-base font-medium")
        ui.label(error_message).classes("text-sm text-red-700")


def _render_table(
    controller: Any, requests: list[dict], on_action: Any
) -> None:
    """Render pending requests as a styled table with inline action buttons."""
    with ui.column().classes("dahlia-my-results-table gap-0 w-full"):
        # Header row
        with ui.row().classes("gap-0 items-center").style(
            "padding: 8px 16px;"
            " border-bottom: 1px solid var(--dahlia-border);"
            " background: rgba(247,247,249,.8);"
        ):
            for label, width in _COLUMNS:
                ui.label(label).classes("dahlia-mono text-xs dahlia-muted").style(
                    f"width: {width}; min-width: {width}; flex-shrink: 0"
                )

        # Data rows
        for idx, req in enumerate(requests):
            border = (
                "border-bottom: 1px solid var(--dahlia-border);"
                if idx < len(requests) - 1
                else ""
            )
            req_id = req.get("request_id")
            user_id = req.get("user_id")
            role_code = req.get("requested_role", "UNKNOWN")
            created_at = str(req.get("created_at", ""))[:19].replace("T", " ")

            role_label, bg, fg = _ROLE_BADGES.get(
                role_code, (role_code, "#f0f0f4", "#6b6b75")
            )

            with ui.row().classes("gap-0 items-center").style(
                f"padding: 10px 16px; min-height: 48px; {border}"
            ):
                # Request ID
                ui.label(f"#{req_id}").classes("dahlia-mono text-sm font-medium").style(
                    "width: 90px; min-width: 90px; flex-shrink: 0"
                )
                # User ID
                ui.label(f"User #{user_id}").classes("text-sm dahlia-muted").style(
                    "width: 100px; min-width: 100px; flex-shrink: 0"
                )
                # Requested Role
                with ui.element("div").style(
                    "width: 160px; min-width: 160px; flex-shrink: 0"
                ):
                    ui.html(
                        f'<span class="dahlia-status-badge" style="background:{bg}; color:{fg};">'
                        f"{role_label}"
                        "</span>",
                        sanitize=False,
                    )
                # Submitted date
                ui.label(created_at).classes("dahlia-mono text-xs dahlia-muted").style(
                    "width: 180px; min-width: 180px; flex-shrink: 0"
                )

                # Actions
                with ui.row().classes("gap-2 items-center").style(
                    "width: 170px; min-width: 170px; flex-shrink: 0"
                ):
                    async def approve(rid: int = req_id) -> None:
                        res = await controller.api_client.approve_role_request(rid)
                        if res.success:
                            ui.notify(
                                res.data.get("message", "Request approved."),
                                type="positive",
                            )
                            await on_action()
                        else:
                            ui.notify(
                                res.error or "Approval failed.",
                                type="warning",
                            )

                    async def reject(rid: int = req_id) -> None:
                        res = await controller.api_client.reject_role_request(rid)
                        if res.success:
                            ui.notify(
                                res.data.get("message", "Request rejected."),
                                type="info",
                            )
                            await on_action()
                        else:
                            ui.notify(
                                res.error or "Rejection failed.",
                                type="warning",
                            )

                    ui.button(
                        "Approve",
                        on_click=approve,
                    ).props("dense unelevated").classes(
                        "text-xs px-2"
                    ).style(
                        "background: #25845d !important; color: white !important; border-radius: 4px;"
                    )

                    ui.button(
                        "Reject",
                        on_click=reject,
                    ).props("dense outline").classes(
                        "text-xs px-2"
                    ).style(
                        "color: #c93f4b !important; border-color: #c93f4b !important; border-radius: 4px;"
                    )
