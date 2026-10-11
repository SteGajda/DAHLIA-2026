"""Profile, Login and Register screens."""

from __future__ import annotations

from typing import Any

from nicegui import ui

from dahlia.app.components.layout import sidebar_page


# Public render functions

def render_profile(controller: Any) -> None:
    """Landing screen for unauthenticated users: Log in / Register / offline."""
    with sidebar_page(controller, "profile", "Profile"):
        with ui.element("main").classes("dahlia-setup-main"):
            with ui.column().classes("dahlia-profile-card gap-0"):
                ui.label("Profile").classes("dahlia-title")
                ui.label(
                    "You can continue to use DAHLIA offline without an account. "
                    "An account is required for uploading results to the database."
                ).classes("text-sm dahlia-muted mb-6")
                ui.button(
                    "Log in",
                    on_click=controller.show_login,
                ).classes("dahlia-primary-btn w-full mb-3")
                ui.button(
                    "Register",
                    on_click=controller.show_register,
                ).classes("dahlia-secondary-btn w-full mb-3")
                ui.button(
                    "Continue offline",
                    on_click=lambda: controller.show_setup(reset_defaults=False),
                ).props("flat no-caps").classes("w-full text-sm mt-1").style(
                    "color: var(--dahlia-muted)"
                )


def render_login(controller: Any, error: str | None = None) -> None:
    """Log-in form screen."""
    with sidebar_page(controller, "profile", "Profile"):
        with ui.element("main").classes("dahlia-setup-main"):
            with ui.column().classes("dahlia-profile-card gap-0"):
                ui.button(
                    "← Back",
                    on_click=controller.show_profile,
                ).props("flat no-caps dense").classes(
                    "dahlia-back-link self-start mb-4"
                )
                ui.label("Log in").classes("dahlia-title")

                if error:
                    ui.label(error).classes("dahlia-error mb-4")

                with ui.column().classes("w-full gap-5"):
                    with ui.column().classes("w-full gap-0"):
                        ui.label("Email").classes("dahlia-field-label")
                        email_input = (
                            ui.input(placeholder="you@example.com")
                            .props("outlined dense type=email")
                            .classes("dahlia-field")
                        )
                    with ui.column().classes("w-full gap-0"):
                        ui.label("Password").classes("dahlia-field-label")
                        password_input = (
                            ui.input(placeholder="••••••••")
                            .props("outlined dense type=password")
                            .classes("dahlia-field")
                        )

                error_label = ui.label("").classes("text-xs text-red-700 mt-2")
                error_label.set_visibility(False)

                async def do_login() -> None:
                    error_label.set_visibility(False)
                    msg = await controller.do_login(
                        email_input.value or "", password_input.value or ""
                    )
                    if msg:
                        error_label.set_text(msg)
                        error_label.set_visibility(True)
                    else:
                        controller.show_profile()

                ui.button("Log in", on_click=do_login).classes(
                    "dahlia-primary-btn w-full mt-5"
                )


def render_register(controller: Any, error: str | None = None) -> None:
    """Registration form screen."""
    with sidebar_page(controller, "profile", "Profile"):
        with ui.element("main").classes("dahlia-setup-main"):
            with ui.column().classes("dahlia-profile-card gap-0"):
                ui.button(
                    "← Back",
                    on_click=controller.show_profile,
                ).props("flat no-caps dense").classes(
                    "dahlia-back-link self-start mb-4"
                )
                ui.label("Register").classes("dahlia-title")

                if error:
                    ui.label(error).classes("dahlia-error mb-4")

                with ui.column().classes("w-full gap-4"):
                    with ui.column().classes("w-full gap-0"):
                        ui.label("Email").classes("dahlia-field-label")
                        email_input = (
                            ui.input(placeholder="you@example.com")
                            .props("outlined dense type=email")
                            .classes("dahlia-field")
                        )
                    with ui.column().classes("w-full gap-0"):
                        ui.label("Username").classes("dahlia-field-label")
                        username_input = (
                            ui.input()
                            .props("outlined dense")
                            .classes("dahlia-field")
                        )
                    with ui.column().classes("w-full gap-0"):
                        ui.label("Password").classes("dahlia-field-label")
                        password_input = (
                            ui.input(placeholder="••••••••")
                            .props("outlined dense type=password")
                            .classes("dahlia-field")
                        )

                    affiliation_check = ui.checkbox(
                        "I am affiliated with Warsaw University of Technology"
                    ).classes("dahlia-checkbox")

                    with ui.column().classes("w-full gap-0") as index_container:
                        ui.label("Student index number").classes(
                            "dahlia-field-label"
                        )
                        index_input = (
                            ui.input(placeholder="e.g. 310123")
                            .props("outlined dense")
                            .classes("dahlia-field dahlia-mono")
                        )
                    index_container.set_visibility(False)

                    def toggle_affiliation(event: Any) -> None:
                        index_container.set_visibility(event.value)
                        if not event.value:
                            index_input.value = ""

                    affiliation_check.on_value_change(toggle_affiliation)

                    consent_check = ui.checkbox(
                        "I agree that my experiment results may be stored and"
                        " processed for research purposes only."
                    ).classes("dahlia-checkbox-consent")

                error_label = ui.label("").classes("text-xs text-red-700 mt-2")
                error_label.set_visibility(False)

                async def submit_register() -> None:
                    await _do_register(
                        controller,
                        email_input,
                        username_input,
                        password_input,
                        affiliation_check,
                        index_input,
                        consent_check,
                        error_label,
                    )

                register_btn = ui.button(
                    "Register",
                    on_click=submit_register,
                ).classes("dahlia-primary-btn w-full mt-3")
                register_btn.disable()

                def toggle_consent(event: Any) -> None:
                    if event.value:
                        register_btn.enable()
                    else:
                        register_btn.disable()

                consent_check.on_value_change(toggle_consent)

                ui.label(
                    "Email verification required after registration."
                ).classes("text-xs text-center dahlia-muted mt-3")


def render_profile_view(controller: Any) -> None:
    """Profile screen for authenticated users."""
    user = controller.current_user
    assert user is not None
    local_count = len(controller.local_experiments)
    role_code = str(user.get("role", "USER")).upper()
    role_labels = {
        "USER": "User",
        "USER_PLUS": "User+",
        "RESEARCHER": "Researcher",
        "DEVELOPER": "Developer",
    }
    role_display = role_labels.get(role_code, role_code)
    sync_status = "Online" if getattr(controller, "is_online", False) else "Offline mode"

    with sidebar_page(controller, "profile", "Profile"):
        with ui.element("main").classes("dahlia-setup-main"):
            with ui.column().classes("dahlia-profile-card gap-0"):
                ui.label("Profile").classes("dahlia-title")

                with ui.column().classes("w-full gap-3 mb-6"):
                    _info_row("Email", user["email"])
                    _info_row("Username", user["username"])
                    _info_row("Role", role_display)
                    if user.get("affiliated"):
                        _info_row(
                            "WUT affiliation",
                            f"Yes — index: {user.get('index_no') or '–'}",
                        )
                    _info_row("Local experiments", str(local_count))
                    _info_row("Sync status", sync_status)

                # Upgrade options strictly one level higher:
                # USER -> USER_PLUS, USER_PLUS -> RESEARCHER
                if role_code == "USER":
                    async def on_request_user_plus() -> None:
                        ok, msg = await controller.request_role("USER_PLUS")
                        ui.notify(
                            msg,
                            type="positive" if ok else "warning",
                            timeout=4000,
                        )

                    ui.button(
                        "Request USER+ role",
                        on_click=on_request_user_plus,
                    ).props("outline no-caps").classes(
                        "dahlia-secondary-btn w-full mb-3"
                    )
                elif role_code == "USER_PLUS":
                    async def on_request_researcher() -> None:
                        ok, msg = await controller.request_role("RESEARCHER")
                        ui.notify(
                            msg,
                            type="positive" if ok else "warning",
                            timeout=4000,
                        )

                    ui.button(
                        "Request RESEARCHER role",
                        on_click=on_request_researcher,
                    ).props("outline no-caps").classes(
                        "dahlia-secondary-btn w-full mb-3"
                    )

                ui.button(
                    "Log out",
                    on_click=controller.logout,
                ).classes("dahlia-danger-btn w-full")


# Private helpers

async def _do_register(
    controller: Any,
    email_input: Any,
    username_input: Any,
    password_input: Any,
    affiliation_check: Any,
    index_input: Any,
    consent_check: Any,
    error_label: Any,
) -> None:
    """Validate and submit the registration form to the backend."""
    error_label.set_visibility(False)
    msg = await controller.do_register(
        email=str(email_input.value or ""),
        username=str(username_input.value or ""),
        password=str(password_input.value or ""),
        affiliated=bool(affiliation_check.value),
        index_no=str(index_input.value or ""),
        agreed=bool(consent_check.value),
    )
    if msg:
        error_label.set_text(msg)
        error_label.set_visibility(True)
    else:
        ui.notify(
            "Account created successfully. Check server logs for activation token.",
            type="positive",
            timeout=5000,
        )
        controller.show_login()


def _info_row(label: str, value: str) -> None:
    """Render a single key–value info pair in the profile view."""
    with ui.row().classes("w-full items-baseline gap-3"):
        ui.label(f"{label}:").classes("dahlia-profile-info-label")
        ui.label(value).classes("text-sm")
