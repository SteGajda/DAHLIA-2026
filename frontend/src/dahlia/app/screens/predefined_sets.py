"""Online predefined set form and unsaved 15-point preview."""

from typing import Any

from nicegui import ui

from dahlia.app.components.layout import sidebar_page
from dahlia.services.config import NA_FRACTIONS
from dahlia.services.predefined_sets import (
    PredefinedDraft, can_manage_predefined_sets, parse_dataset_catalog,
)


def render_predefined_sets(controller: Any) -> None:
    if not can_manage_predefined_sets(controller.current_user):
        controller.show_profile()
        return
    draft = PredefinedDraft()
    catalog = {}
    marker = object()
    controller._predefined_screen_marker = marker
    owner = controller.current_user.get("user_id")

    def still_current() -> bool:
        return (controller.active_screen == "predefined_sets"
                and controller._predefined_screen_marker is marker
                and can_manage_predefined_sets(controller.current_user)
                and controller.current_user.get("user_id") == owner)

    with sidebar_page(controller, "predefined_sets", "Predefined Sets"):
        with ui.element("main").classes("dahlia-content-main w-full"):
            with ui.column().classes("w-full gap-5").style("max-width: 900px; margin: 0 auto"):
                with ui.row().classes("w-full items-center justify-between"):
                    ui.label("Create predefined set").classes("dahlia-title mb-0")
                    refresh = ui.button("Refresh datasets", icon="refresh").props("outline no-caps")
                with ui.row().classes("items-center gap-2"):
                    spinner = ui.spinner(size="22px")
                    status = ui.label("Loading datasets...").classes("text-sm dahlia-muted")
                with ui.column().classes("w-full gap-4 rounded-lg border p-6 bg-white"):
                    dataset_select = ui.select({}, label="Dataset").props("outlined dense").classes("w-full")
                    fraction_select = ui.select(
                        list(NA_FRACTIONS), value=draft.na_fraction, label="NA fraction",
                    ).props("outlined dense").classes("w-full")
                    hint = ui.label("Select a dataset to see the required count and index range.").classes("text-sm dahlia-muted")
                    removed_input = ui.textarea(label="All removed row indices", value="").props(
                        "outlined rows=3 placeholder=\"0, 1, 2, ...\""
                    ).classes("w-full dahlia-mono")
                    annotation_input = ui.textarea(label="Evaluation row indices (optional)", value="").props(
                        "outlined rows=2 placeholder=\"15 indices in presentation order\""
                    ).classes("w-full dahlia-mono")
                    ui.label("Leave the second field empty to draw 15 points and their presentation order.").classes("text-sm dahlia-muted")
                    error = ui.label("").classes("text-sm text-red-700")
                    error.set_visibility(False)
                    prepare = ui.button("Prepare preview").props("no-caps").classes("dahlia-primary-btn")
                preview = ui.column().classes("w-full gap-3 rounded-lg border p-6 bg-white")
                preview.set_visibility(False)

    controls = [dataset_select, fraction_select, removed_input, annotation_input, prepare]
    for control in controls:
        control.disable()

    def invalidate() -> None:
        preview.clear()
        preview.set_visibility(False)
        error.set_text("")
        error.set_visibility(False)

    def update_configuration() -> None:
        draft.select_dataset(catalog.get(dataset_select.value))
        draft.select_fraction(fraction_select.value)
        removed_input.value = draft.removed_text
        annotation_input.value = draft.annotation_text
        invalidate()
        if draft.dataset is None:
            hint.set_text("Select a dataset to see the required count and index range.")
            prepare.disable()
            return
        hint.set_text(f"Enter exactly {draft.missing_count} removed indices. "
                      f"Allowed row_index: 0-{draft.dataset.row_count - 1} "
                      f"({draft.dataset.row_count} rows).")
        if draft.missing_count < 15:
            error.set_text("This fraction produces fewer than 15 missing points. Choose another configuration.")
            error.set_visibility(True)
            prepare.disable()
        else:
            prepare.enable()

    def change_removed(event: Any) -> None:
        value = str(event.value or "")
        if value != draft.removed_text:
            draft.set_removed_text(value)
            invalidate()

    def change_annotations(event: Any) -> None:
        value = str(event.value or "")
        if value != draft.annotation_text:
            draft.set_annotation_text(value)
            invalidate()

    def prepare_preview() -> None:
        if not still_current():
            return
        invalidate()
        try:
            result = draft.prepare_preview()
        except ValueError as exc:
            error.set_text(str(exc))
            error.set_visibility(True)
            return
        annotation_input.value = draft.annotation_text
        with preview:
            ui.label("Preview").classes("text-lg font-semibold")
            ui.label(f"{result.dataset.name} | NA fraction {result.na_fraction} | "
                     f"{len(result.removed_indices)} removed points").classes("text-sm dahlia-muted")
            ui.label("Evaluation order").classes("text-sm font-medium")
            with ui.row().classes("w-full gap-2"):
                for order, index in enumerate(result.annotation_indices, start=1):
                    ui.label(f"{order}.  row {index}").classes(
                        "dahlia-mono text-sm rounded border px-3 py-2"
                    )
            ui.label("Preview only - this set has not been saved.").classes("text-sm dahlia-muted")
        preview.set_visibility(True)

    async def load_datasets() -> None:
        if not still_current():
            return
        refresh.disable()
        for control in controls:
            control.disable()
        draft.select_dataset(None)
        draft.clear_points()
        catalog.clear()
        dataset_select.set_options({}, value=None)
        removed_input.value = ""
        annotation_input.value = ""
        invalidate()
        hint.set_text("Select a dataset to see the required count and index range.")
        spinner.set_visibility(True)
        status.set_text("Loading datasets...")
        res = await controller.api_client.list_active_datasets()
        if not still_current():
            return
        spinner.set_visibility(False)
        refresh.enable()
        controller.is_online = not res.is_offline
        controller._update_status_badge()
        if not res.success:
            if res.is_offline:
                message = "Internet connection is required to create predefined sets. Retry when connected."
            elif res.status_code == 401:
                message = "Your session has expired. Sign in again from Profile."
            else:
                message = res.error or "Could not load datasets."
            status.set_text(message)
            return
        try:
            datasets = parse_dataset_catalog(res.data)
        except ValueError as exc:
            status.set_text(str(exc))
            return
        if not datasets:
            status.set_text("No active datasets are available.")
            return
        catalog.update({item.dataset_id: item for item in datasets})
        dataset_select.set_options({item.dataset_id: item.name for item in datasets})
        for control in controls:
            control.enable()
        prepare.disable()
        status.set_text("Choose a dataset and prepare the point lists.")

    dataset_select.on_value_change(lambda _: update_configuration())
    fraction_select.on_value_change(lambda _: update_configuration())
    removed_input.on_value_change(change_removed)
    annotation_input.on_value_change(change_annotations)
    prepare.on_click(prepare_preview)
    refresh.on_click(load_datasets)
    ui.timer(0.01, load_datasets, once=True)
