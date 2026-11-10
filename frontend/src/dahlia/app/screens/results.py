"""Results Summary screen."""

from __future__ import annotations

from typing import Any

from nicegui import ui

from dahlia.app.components.layout import sidebar_page


def render_results(controller: Any) -> None:
    """Results Summary screen shown after completing an experiment."""
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

    with sidebar_page(controller, "setup", "Results Summary"):
        with ui.element("main").classes("dahlia-results-main"):
            with ui.column().classes("dahlia-results gap-0"):
                # Success indicator
                with ui.row().classes("items-center gap-2 mb-3"):
                    ui.icon("check_circle").classes("text-positive")
                    ui.label("Results saved locally").classes(
                        "text-sm text-positive font-medium"
                    )

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

                # Action buttons
                def _export_current() -> None:
                    """Export metrics + answers CSVs for the just-finished experiment."""
                    if not controller.local_experiments:
                        return
                    current = [controller.local_experiments[-1]]
                    controller.export_local_csv_metrics(current)
                    controller.export_local_csv_answers(current)

                ui.button(
                    "Export this experiment",
                    on_click=_export_current,
                ).props("outline no-caps").classes("dahlia-secondary-btn w-full mb-2")

                if controller.current_user is not None:
                    ui.button(
                        "Upload to database",
                        on_click=lambda: ui.notify(
                            "Database upload is not yet implemented.",
                            type="info",
                        ),
                    ).props("outline no-caps").classes(
                        "dahlia-secondary-btn w-full mb-2"
                    )

                ui.button(
                    "Back to main menu",
                    on_click=lambda: controller.show_setup(reset_defaults=False),
                ).classes("dahlia-primary-btn w-full")
