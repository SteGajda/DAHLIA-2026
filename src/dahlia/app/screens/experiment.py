"""Active Experiment screen."""

from __future__ import annotations

from html import escape
from typing import Any

from nicegui import ui

from dahlia.app.components.branding import brand
from dahlia.app.components.chart import (
    PLOTLY_CONFIG,
    build_experiment_figure,
)
from dahlia.services.config import TOTAL_STEPS
from dahlia.services.experiment import precision_digits


def _tick_markup(experiment: Any) -> str:
    digits = precision_digits(experiment.config.precision)
    items = "".join(
        f'<span class="dahlia-tick">{escape(f"{value:.{digits}f}")}</span>'
        for value in experiment.display_ticks
    )
    return f'<div class="dahlia-tick-row">{items}</div>'


def _figure_payload(experiment: Any, predicted_value: float) -> dict:
    payload = build_experiment_figure(
        experiment,
        predicted_value,
    ).to_plotly_json()
    payload["config"] = PLOTLY_CONFIG
    return payload


def render_experiment(controller: Any) -> None:
    experiment = controller.experiment
    assert experiment is not None
    digits = precision_digits(experiment.config.precision)

    restart_dialog = ui.dialog()
    with restart_dialog, ui.card().classes("dahlia-modal-card gap-0"):
        ui.label("Restart experiment?").classes("dahlia-modal-title mb-2")
        ui.label(
            "All progress in the current experiment will be lost. "
            "Previously saved experiments will not be affected."
        ).classes("dahlia-modal-copy mb-5")
        with ui.row().classes("w-full justify-end gap-2"):
            ui.button("Cancel", on_click=restart_dialog.close).classes(
                "dahlia-secondary-btn px-4"
            )
            ui.button(
                "Restart experiment",
                on_click=controller.restart_experiment,
            ).classes("dahlia-danger-btn px-4")

    with ui.column().classes("dahlia-setup-page gap-0"):
        with ui.row().classes("dahlia-header items-center no-wrap"):
            brand()
            ui.space()
            ui.label(
                f"Imputation {experiment.current_step}/{TOTAL_STEPS}"
            ).classes("dahlia-mono text-xs dahlia-muted")
            ui.space()
            ui.button(
                "Restart experiment",
                on_click=restart_dialog.open,
            ).props("flat no-caps dense").classes("dahlia-link text-xs")

        with ui.row().classes("dahlia-settings-bar items-center"):
            with ui.row().classes("dahlia-summary items-center"):
                ui.html(
                    f'dataset <b>{escape(experiment.config.name)}</b>'
                )
                ui.html(f'NA <b>{experiment.na_fraction}</b>')
                ui.html(
                    f'proj <b>{escape(experiment.projection_name)}</b>'
                )
                ui.html(f'seed <b>{experiment.seed}</b>')

        with ui.element("main").classes("dahlia-experiment-main"):
            with ui.column().classes("dahlia-experiment-content gap-0"):
                with ui.element("div").classes("dahlia-chart-frame"):
                    chart = ui.plotly(
                        _figure_payload(
                            experiment,
                            controller.current_prediction,
                        )
                    ).classes("w-full h-full")

                value_text = ui.html(
                    f'{escape(experiment.config.incomplete_column)} = '
                    f'<b>{controller.current_prediction:.{digits}f}</b>'
                ).classes("dahlia-prediction-label mb-1")

                slider = (
                    ui.slider(
                        min=experiment.value_min,
                        max=experiment.value_max,
                        step=experiment.config.precision,
                        value=controller.current_prediction,
                        on_change=controller.prediction_from_slider,
                    )
                    .props("label-always=false")
                    .classes("dahlia-slider w-full")
                )
                ui.html(_tick_markup(experiment), sanitize=False).classes("w-full")

                with ui.row().classes(
                    "dahlia-controls items-end no-wrap gap-3"
                ):
                    with ui.column().classes("gap-1"):
                        ui.label("Predicted value").classes(
                            "dahlia-prediction-label"
                        )
                        number_input = (
                            ui.input(
                                value=(
                                    f"{controller.current_prediction:.{digits}f}"
                                ),
                                on_change=controller.prediction_from_input,
                            )
                            .props(
                                "outlined dense "
                                f"type=number min={experiment.value_min} "
                                f"max={experiment.value_max} "
                                f"step={experiment.config.precision}"
                            )
                            .classes("dahlia-number")
                        )
                        number_input.on(
                            "blur",
                            lambda: controller.restore_prediction_input(),
                        )
                    ui.space()
                    ui.button(
                        "Restart",
                        on_click=restart_dialog.open,
                    ).classes("dahlia-secondary-btn px-5")
                    next_text = (
                        "Finish experiment"
                        if experiment.current_step == TOTAL_STEPS
                        else "Next →"
                    )
                    next_button = ui.button(
                        next_text,
                        on_click=controller.confirm_current_prediction,
                    ).classes("dahlia-primary-btn px-6")

    with ui.element("div").classes("dahlia-loading-overlay") as result_overlay:
        with ui.column().classes("dahlia-loading-box items-center gap-3"):
            ui.spinner(size="34px", color="primary")
            ui.label("Calculating results…").classes("text-sm font-medium")
    result_overlay.set_visibility(False)

    controller.bind_experiment_elements(
        chart=chart,
        slider=slider,
        number_input=number_input,
        value_text=value_text,
        next_button=next_button,
        result_overlay=result_overlay,
    )
    controller.start_prediction_monitor()
