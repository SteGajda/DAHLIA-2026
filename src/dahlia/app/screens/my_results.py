"""My Results screen."""

from __future__ import annotations

from html import escape
from typing import Any

from nicegui import ui

from dahlia.app.components.layout import sidebar_page

_SYNC_CSS: dict[str, str] = {
    "Local only": "dahlia-sync-local",
    "Sync pending": "dahlia-sync-pending",
    "Synced": "dahlia-sync-synced",
    "Sync failed": "dahlia-sync-failed",
}

_COLUMNS: list[tuple[str, str]] = [
    ("DATE", "150px"),
    ("DATASET", "100px"),
    ("SEED / SET ID", "130px"),
    ("NA", "60px"),
    ("PROJECTION", "110px"),
    ("SYNC STATUS", "125px"),
    ("ACTIONS", "110px"),
]

_EXPORT_FORMATS = ["CSV", "XLSX", "PDF"]


def render_my_results(controller: Any) -> None:
    """My Results screen: list, export and manage local experiment records."""
    experiments = controller.local_experiments

    with sidebar_page(controller, "my_results", "My Results"):
        with ui.element("main").classes("dahlia-content-main"):
            ui.label("My Results").classes("dahlia-title")
            ui.label(
                "Results are stored locally on this device and can be exported "
                "or uploaded to the database."
            ).classes("text-sm dahlia-muted mb-5")

            # Export controls
            with ui.row().classes("items-center gap-2 mb-5 flex-wrap"):
                format_select = (
                    ui.select(_EXPORT_FORMATS, value="CSV")
                    .props("outlined dense")
                    .style("min-width: 80px")
                    .classes("dahlia-field")
                )

                def _export_metrics_all() -> None:
                    if format_select.value == "CSV":
                        controller.export_local_csv_metrics()
                    else:
                        ui.notify(
                            f"{format_select.value} export coming soon.",
                            type="info",
                        )

                def _export_answers_all() -> None:
                    if format_select.value == "CSV":
                        controller.export_local_csv_answers()
                    else:
                        ui.notify(
                            f"{format_select.value} export coming soon.",
                            type="info",
                        )

                ui.button(
                    "Export metrics",
                    on_click=_export_metrics_all,
                ).classes("dahlia-export-btn active").tooltip(
                    "Export MAE/RMSE summary for all local experiments"
                )
                ui.button(
                    "Export answers",
                    on_click=_export_answers_all,
                ).classes("dahlia-export-btn active").tooltip(
                    "Export per-point annotator answers for all local experiments"
                )

                ui.space()

                ui.button(
                    "↑  Upload to database",
                    on_click=lambda: ui.notify(
                        "Database upload is not yet implemented in this version.",
                        type="info",
                    ),
                ).props("outline no-caps").classes("dahlia-secondary-btn")

            # Experiments table or empty state
            if not experiments:
                _render_empty_state()
            else:
                _render_table(controller, experiments)


def _render_empty_state() -> None:
    """Placeholder shown when no local experiments have been saved yet."""
    with ui.column().classes("items-center w-full py-16 gap-3"):
        ui.icon("inbox").classes("text-5xl dahlia-muted")
        ui.label("No local results yet.").classes("text-base font-medium")
        ui.label(
            "Complete an experiment to see your results here."
        ).classes("text-sm dahlia-muted")
        ui.label(
            "Per-experiment analytics and filtering are planned for a future version."
        ).classes("text-xs dahlia-muted mt-1")


def _render_table(controller: Any, experiments: list[dict]) -> None:
    """Render local experiments as a styled, fixed-column table with per-row actions.

    Uses plain NiceGUI rows rather than ``ui.table`` to allow direct Python
    callbacks on the action buttons without relying on Vue ``$emit`` propagation.
    """
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
        for idx, exp in enumerate(experiments):
            border = (
                "border-bottom: 1px solid var(--dahlia-border);"
                if idx < len(experiments) - 1
                else ""
            )
            css = _SYNC_CSS.get(exp["sync_status"], "dahlia-sync-local")

            with ui.row().classes("gap-0 items-center").style(
                f"padding: 10px 16px; {border}"
            ):
                ui.label(exp["date"]).classes("text-sm").style(
                    f"width: {_COLUMNS[0][1]}; min-width: {_COLUMNS[0][1]}; flex-shrink: 0"
                )
                ui.label(exp["dataset"]).classes("text-sm dahlia-mono").style(
                    f"width: {_COLUMNS[1][1]}; min-width: {_COLUMNS[1][1]}; flex-shrink: 0"
                )
                ui.label(str(exp["seed"])).classes("text-sm dahlia-mono").style(
                    f"width: {_COLUMNS[2][1]}; min-width: {_COLUMNS[2][1]}; flex-shrink: 0"
                )
                ui.label(str(exp["na_fraction"])).classes("text-sm dahlia-mono").style(
                    f"width: {_COLUMNS[3][1]}; min-width: {_COLUMNS[3][1]}; flex-shrink: 0"
                )
                ui.label(exp["projection"]).classes("text-sm dahlia-mono").style(
                    f"width: {_COLUMNS[4][1]}; min-width: {_COLUMNS[4][1]}; flex-shrink: 0"
                )
                ui.html(
                    f'<span class="dahlia-status-badge {css}">'
                    f"{escape(exp['sync_status'])}</span>",
                    sanitize=False,
                ).style(
                    f"width: {_COLUMNS[5][1]}; min-width: {_COLUMNS[5][1]}; flex-shrink: 0"
                )
                # Per-row actions (view metrics | export this row | delete)
                with ui.row().classes("gap-1 items-center").style(
                    f"width: {_COLUMNS[6][1]}; min-width: {_COLUMNS[6][1]}; flex-shrink: 0"
                ):
                    ui.button(
                        icon="visibility",
                        on_click=lambda e, i=idx: _open_results_dialog(experiments[i]),
                    ).props("flat round dense size=sm color=grey-6").tooltip("View metrics")
                    ui.button(
                        icon="download",
                        on_click=lambda e, i=idx: _export_single(controller, experiments[i]),
                    ).props("flat round dense size=sm color=grey-6").tooltip(
                        "Export this experiment (metrics + answers)"
                    )
                    ui.button(
                        icon="delete",
                        on_click=lambda e, i=idx: _open_delete_dialog(controller, i),
                    ).props("flat round dense size=sm color=negative").tooltip(
                        "Delete from local records"
                    )


def _export_single(controller: Any, exp: dict) -> None:
    """Export metrics and answers CSVs for a single experiment record."""
    controller.export_local_csv_metrics([exp])
    controller.export_local_csv_answers([exp])


def _open_results_dialog(exp: dict) -> None:
    """Open a modal dialog showing the MAE/RMSE results for one experiment."""
    dialog = ui.dialog()
    with dialog, ui.card().classes("dahlia-modal-card gap-3"):
        with ui.row().classes("items-center justify-between w-full"):
            ui.label(
                f"{exp['dataset']} · seed {exp['seed']} · {exp['date']}"
            ).classes("text-sm font-medium")
            ui.button(icon="close", on_click=dialog.close).props(
                "flat round dense"
            )

        results_df = exp.get("results")
        if results_df is not None and not results_df.empty:
            mae_vals = results_df["MAE"].astype(float).tolist()
            rmse_vals = results_df["RMSE"].astype(float).tolist()
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
                for row in results_df.itertuples(index=False)
            ]
            columns = [
                {
                    "name": "Method",
                    "label": "Method",
                    "field": "Method",
                    "align": "left",
                },
                {"name": "MAE", "label": "MAE", "field": "MAE", "align": "right"},
                {
                    "name": "RMSE",
                    "label": "RMSE",
                    "field": "RMSE",
                    "align": "right",
                },
            ]
            detail_table = (
                ui.table(columns=columns, rows=rows, row_key="Method")
                .props("flat hide-bottom dense")
                .classes("dahlia-results-table w-full")
            )
            detail_table.add_slot(
                "body-cell-MAE",
                r"""
                <q-td :props="props" style="text-align: right">
                    <b v-if="props.row.best_mae">{{ props.value }}</b>
                    <span v-else>{{ props.value }}</span>
                </q-td>
                """,
            )
            detail_table.add_slot(
                "body-cell-RMSE",
                r"""
                <q-td :props="props" style="text-align: right">
                    <b v-if="props.row.best_rmse">{{ props.value }}</b>
                    <span v-else>{{ props.value }}</span>
                </q-td>
                """,
            )
        else:
            ui.label("Results data unavailable.").classes("text-sm dahlia-muted")

    dialog.open()


def _open_delete_dialog(controller: Any, idx: int) -> None:
    """Show a confirmation modal before deleting a local experiment record."""
    dialog = ui.dialog()
    with dialog, ui.card().classes("dahlia-modal-card gap-0"):
        ui.label("Delete experiment?").classes("dahlia-modal-title mb-2")
        ui.label(
            "This record will be removed from your local device. "
            "This action cannot be undone."
        ).classes("dahlia-modal-copy mb-5")
        with ui.row().classes("w-full justify-end gap-2"):
            ui.button("Cancel", on_click=dialog.close).classes(
                "dahlia-secondary-btn px-4"
            )
            ui.button(
                "Delete",
                on_click=lambda e: controller.delete_local_experiment(idx),
            ).classes("dahlia-danger-btn px-4")
    dialog.open()
