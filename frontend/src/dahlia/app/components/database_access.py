"""Connection details for personal, read-only SSMS accounts."""

from typing import Any

from nicegui import ui

READ_ROLES = {"USER_PLUS", "RESEARCHER", "DEVELOPER"}


def render_database_access(controller: Any) -> None:
    user = controller.current_user or {}
    role = str(user.get("role", "USER")).upper()
    owner = user.get("user_id")
    ui.separator().classes("my-4")
    ui.label("Database access (SSMS)").classes("text-base font-medium mb-2")
    if role not in READ_ROLES:
        ui.label("Read-only SQL access is available for User+, Researcher and Developer accounts.").classes(
            "text-sm dahlia-muted mb-3"
        )
        return
    if not user.get("is_email_verified"):
        ui.label("Verify your email address to activate SQL access.").classes("text-sm dahlia-muted mb-3")
        return
    ui.label(
        "Read-only access to shared experiment data. Account emails, passwords and session tokens are excluded."
    ).classes("text-sm dahlia-muted mb-3")
    ip_input = ui.input(label="Your public IPv4 address", placeholder="e.g. your home or university public IP").props(
        "outlined dense"
    ).classes("w-full mb-3")
    ui.label(
        "Use the public IPv4 of the network where you will run SSMS. "
        "Generating credentials also allows this IP through the database firewall."
    ).classes("text-xs dahlia-muted mb-3")

    def same_account():
        return controller.current_user is not None and controller.current_user.get("user_id") == owner

    def show_details(data, with_password=False):
        dialog = ui.dialog()
        with dialog, ui.card().classes("w-full max-w-xl"):
            ui.label("SSMS connection").classes("text-lg font-medium")
            for label, value in (
                ("Server", data.get("server", "")),
                ("Database", data.get("database", "")),
                ("Authentication", "SQL Server Authentication"),
                ("Username", data.get("username") or "Not activated"),
                ("Public IPv4", data.get("client_ipv4") or "Not set"),
            ):
                ui.input(label=label, value=value).props("readonly outlined dense").classes("w-full")
            if with_password:
                password_input = ui.input(label="SQL password", value=data["password"],
                                           password=True, password_toggle_button=True).props("readonly outlined dense").classes("w-full")
                ui.label("Save the password now. It cannot be displayed again. Generating another password replaces it.").classes(
                    "text-sm text-amber-800"
                )
                # Remove the secret from the UI model when the dialog closes.
                dialog.on("hide", lambda: password_input.set_value(""))
            ui.label("Choose database DAHLIA before connecting. Enable encryption and keep certificate verification enabled.").classes(
                "text-sm dahlia-muted"
            )
            ui.button("Close", on_click=dialog.close)
        dialog.on("hide", dialog.delete)
        dialog.open()

    async def status():
        result = await controller.api_client.get_database_access()
        if not same_account():
            return
        if not result.success:
            ui.notify(result.error or "Could not read SQL access details.", type="warning")
        elif not result.data.get("eligible"):
            ui.notify("Your account is not currently eligible for SQL access.", type="warning")
        elif not result.data.get("configured"):
            ui.notify("The administrator has not enabled SQL account activation yet.", type="warning")
        else:
            show_details(result.data)

    async def issue():
        issue_button.disable()
        try:
            result = await controller.api_client.issue_sql_credentials(ip_input.value or "")
            if not same_account():
                return
            if not result.success:
                ui.notify(result.error or "Could not activate SQL access.", type="warning", timeout=8000)
                return
            show_details(result.data, with_password=True)
        finally:
            issue_button.enable()

    ui.button("Show SQL connection details", on_click=status).classes("dahlia-secondary-btn w-full mb-3")
    with ui.dialog() as confirmation, ui.card():
        ui.label("Generate SQL credentials?").classes("text-lg font-medium")
        ui.label("If you already have a SQL password, it will be replaced. Other users' accounts will not change.")
        with ui.row():
            ui.button("Cancel", on_click=confirmation.close)
            async def confirm():
                confirmation.close()
                await issue()
            ui.button("Generate", on_click=confirm)
    issue_button = ui.button("Activate / reset SQL access", on_click=confirmation.open).classes(
        "dahlia-secondary-btn w-full mb-3"
    )
