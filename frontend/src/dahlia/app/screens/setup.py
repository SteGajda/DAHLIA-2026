"""Experiment Setup screen."""

from __future__ import annotations

from typing import Any

from nicegui import ui

from dahlia.app.components.layout import sidebar_page
from dahlia.services.config import DATASETS, MAX_SEED, NA_FRACTIONS, PROJECTIONS


def render_setup(controller: Any, error_message: str | None = None) -> None:
    with sidebar_page(controller, "setup"):
        with ui.element("main").classes("dahlia-setup-main"):
            with ui.column().classes("dahlia-card gap-0"):
                ui.label("Experiment Setup").classes("dahlia-title")

                if error_message:
                    ui.label(error_message).classes("dahlia-error mb-5")

                with ui.column().classes("w-full gap-5"):
                    with ui.column().classes("w-full gap-0"):
                        ui.label("Insert seed").classes("dahlia-field-label")
                        with ui.row().classes("w-full items-start gap-2 no-wrap"):
                            seed_input = (
                                ui.input(value=str(controller.seed))
                                .props(
                                    f"outlined dense type=number min=0 max={MAX_SEED} step=1"
                                )
                                .classes("dahlia-field dahlia-mono flex-1")
                            )
                            random_button = (
                                ui.button(
                                    "Random seed",
                                    on_click=lambda: controller.generate_random_seed(),
                                )
                                .props("outline no-caps")
                                .classes("dahlia-secondary-btn whitespace-nowrap")
                            )
                        seed_error = ui.label("").classes(
                            "text-xs text-red-700 mt-1"
                        )
                        seed_error.set_visibility(False)

                    with ui.column().classes("w-full gap-0"):
                        ui.label("Select dataset").classes("dahlia-field-label")
                        dataset_select = (
                            ui.select(
                                list(DATASETS),
                                value=controller.dataset_name,
                                on_change=lambda event: setattr(
                                    controller,
                                    "dataset_name",
                                    str(event.value),
                                ),
                            )
                            .props("outlined dense options-dense")
                            .classes("dahlia-field dahlia-mono")
                        )

                    with ui.column().classes("w-full gap-0"):
                        ui.label("Select NA fraction").classes(
                            "dahlia-field-label"
                        )
                        fraction_select = (
                            ui.select(
                                [str(value) for value in NA_FRACTIONS],
                                value=str(controller.na_fraction),
                                on_change=lambda event: setattr(
                                    controller,
                                    "na_fraction",
                                    float(event.value),
                                ),
                            )
                            .props("outlined dense options-dense")
                            .classes("dahlia-field dahlia-mono")
                        )

                    with ui.column().classes("w-full gap-0"):
                        ui.label("Select projection").classes(
                            "dahlia-field-label"
                        )
                        projection_select = (
                            ui.select(
                                list(PROJECTIONS),
                                value=controller.projection_name,
                                on_change=lambda event: setattr(
                                    controller,
                                    "projection_name",
                                    str(event.value),
                                ),
                            )
                            .props("outlined dense options-dense")
                            .classes("dahlia-field dahlia-mono")
                        )

                start_button = (
                    ui.button(
                        "Start Experiment",
                        on_click=controller.start_experiment,
                    )
                    .classes("dahlia-primary-btn w-full mt-8")
                )

    with ui.element("div").classes("dahlia-loading-overlay") as loading_overlay:
        with ui.column().classes("dahlia-loading-box items-center gap-3"):
            ui.spinner(size="34px", color="primary")
            ui.label("Preparing experiment…").classes("text-sm font-medium")
    loading_overlay.set_visibility(False)

    def validate_seed(event: Any) -> None:
        message = controller.set_seed_text(event.value)
        seed_error.set_text(message or "")
        seed_error.set_visibility(bool(message))
        if message:
            seed_input.props("error")
            start_button.disable()
        else:
            seed_input.props(remove="error")
            start_button.enable()

    seed_input.on_value_change(validate_seed)
    controller.bind_setup_elements(
        seed_input=seed_input,
        seed_error=seed_error,
        start_button=start_button,
        loading_overlay=loading_overlay,
        controls=[
            seed_input,
            random_button,
            dataset_select,
            fraction_select,
            projection_select,
            start_button,
        ],
    )
