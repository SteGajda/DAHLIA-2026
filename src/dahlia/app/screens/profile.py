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

                def do_login() -> None:
                    msg = controller.mock_login(
                        email_input.value, password_input.value
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

                register_btn = ui.button(
                    "Register",
                    on_click=lambda: _do_register(
                        controller,
                        email_input,
                        username_input,
                        password_input,
                        affiliation_check,
                        index_input,
                        consent_check,
                        error_label,
                    ),
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

    with sidebar_page(controller, "profile", "Profile"):
        with ui.element("main").classes("dahlia-setup-main"):
            with ui.column().classes("dahlia-profile-card gap-0"):
                ui.label("Profile").classes("dahlia-title")

                with ui.column().classes("w-full gap-3 mb-6"):
                    _info_row("Email", user["email"])
                    _info_row("Username", user["username"])
                    _info_row("Role", user.get("role", "User"))
                    if user.get("affiliated"):
                        _info_row(
                            "WUT affiliation",
                            f"Yes — index: {user.get('index_no') or '–'}",
                        )
                    _info_row("Local experiments", str(local_count))
                    _info_row("Sync status", "Offline mode")

                ui.button(
                    "Request higher role",
                    on_click=lambda: ui.notify(
                        "Role requests are not yet supported in this version.",
                        type="info",
                    ),
                ).props("outline no-caps").classes("dahlia-secondary-btn w-full mb-3")

                ui.button(
                    "Log out",
                    on_click=controller.logout,
                ).classes("dahlia-danger-btn w-full")


# Private helpers

def _do_register(
    controller: Any,
    email_input: Any,
    username_input: Any,
    password_input: Any,
    affiliation_check: Any,
    index_input: Any,
    consent_check: Any,
    error_label: Any,
) -> None:
    """Validate and submit the registration form."""
    msg = controller.mock_register(
        email=email_input.value,
        username=username_input.value,
        password=password_input.value,
        affiliated=bool(affiliation_check.value),
        index_no=str(index_input.value or ""),
        agreed=bool(consent_check.value),
    )
    if msg:
        error_label.set_text(msg)
        error_label.set_visibility(True)
    else:
        ui.notify(
            "Registration submitted. Please verify your email before logging in.",
            type="positive",
            timeout=5000,
        )
        controller.show_profile()


def _info_row(label: str, value: str) -> None:
    """Render a single key–value info pair in the profile view."""
    with ui.row().classes("w-full items-baseline gap-3"):
        ui.label(f"{label}:").classes("dahlia-profile-info-label")
        ui.label(value).classes("text-sm")
