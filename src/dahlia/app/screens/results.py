"""Results Summary screen."""

from __future__ import annotations

from typing import Any

from nicegui import ui

from dahlia.app.components.branding import brand


def render_results(controller: Any) -> None:
    assert controller.results is not None
    rows = [
        {
            "Method": str(row.Method),
            "MAE": f"{float(row.MAE):.6f}",
            "RMSE": f"{float(row.RMSE):.6f}",
        }
        for row in controller.results.itertuples(index=False)
    ]
    columns = [
        {
            "name": "Method",
            "label": "Method",
            "field": "Method",
            "align": "left",
        },
        {
            "name": "MAE",
            "label": "MAE",
            "field": "MAE",
            "align": "right",
        },
        {
            "name": "RMSE",
            "label": "RMSE",
            "field": "RMSE",
            "align": "right",
        },
    ]

    with ui.column().classes("dahlia-setup-page gap-0"):
        with ui.row().classes("dahlia-header items-center"):
            brand()

        with ui.element("main").classes("dahlia-results-main"):
            with ui.column().classes("dahlia-results gap-0"):
                ui.label("Results Summary").classes("dahlia-title")
                ui.table(
                    columns=columns,
                    rows=rows,
                    row_key="Method",
                    pagination={"rowsPerPage": 0},
                ).props("flat hide-bottom").classes(
                    "dahlia-results-table mb-6"
                )
                ui.button(
                    "Start new experiment",
                    on_click=controller.start_new_experiment,
                ).classes("dahlia-primary-btn w-full")
