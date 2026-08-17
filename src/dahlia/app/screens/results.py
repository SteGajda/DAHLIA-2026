"""Results Summary screen."""

from __future__ import annotations

from typing import Any

from nicegui import ui

from dahlia.app.components.branding import brand


def render_results(controller: Any) -> None:
    assert controller.results is not None

    mae_vals = [float(row.MAE) for row in controller.results.itertuples(index=False)]
    rmse_vals = [float(row.RMSE) for row in controller.results.itertuples(index=False)]
    best_mae = min(mae_vals)
    best_rmse = min(rmse_vals)

    rows = [
        {
            "Method": str(row.Method),
            "MAE": f"{float(row.MAE):.4f}",
            "RMSE": f"{float(row.RMSE):.4f}",
            "best_mae": float(row.MAE) <= best_mae + 1e-12,
            "best_rmse": float(row.RMSE) <= best_rmse + 1e-12,
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
                table = (
                    ui.table(
                        columns=columns,
                        rows=rows,
                        row_key="Method",
                        pagination={"rowsPerPage": 0},
                    )
                    .props("flat hide-bottom")
                    .classes("dahlia-results-table mb-6")
                )
                table.add_slot(
                    "body-cell-MAE",
                    r"""
                    <q-td :props="props" style="text-align: right">
                        <b v-if="props.row.best_mae">{{ props.value }}</b>
                        <span v-else>{{ props.value }}</span>
                    </q-td>
                    """,
                )
                table.add_slot(
                    "body-cell-RMSE",
                    r"""
                    <q-td :props="props" style="text-align: right">
                        <b v-if="props.row.best_rmse">{{ props.value }}</b>
                        <span v-else>{{ props.value }}</span>
                    </q-td>
                    """,
                )
                ui.button(
                    "Start new experiment",
                    on_click=controller.start_new_experiment,
                ).classes("dahlia-primary-btn w-full")

