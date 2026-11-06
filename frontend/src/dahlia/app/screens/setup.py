"""Experiment Setup screen."""

from __future__ import annotations

from typing import Any

from nicegui import ui

from dahlia.app.components.layout import sidebar_page
from dahlia.services.config import DATASETS, MAX_SEED, NA_FRACTIONS, PROJECTIONS


def render_setup(controller: Any, error_message: str | None = None) -> None:
    marker = object()
    controller._setup_screen_marker = marker
    catalog = {}
    generation = 0
    downloading = False
    wanted_id = getattr(getattr(controller, "predefined_selection", None), "predefined_set_id", None)
    controller.predefined_selection = None
    controller.experiment_source = getattr(controller, "experiment_source", "SEEDED")

    def still_current() -> bool:
        return controller.active_screen == "setup" and controller._setup_screen_marker is marker

    with sidebar_page(controller, "setup"):
        with ui.element("main").classes("dahlia-setup-main"):
            with ui.column().classes("dahlia-card gap-0"):
                ui.label("Experiment Setup").classes("dahlia-title")

                if error_message:
                    ui.label(error_message).classes("dahlia-error mb-5")

                with ui.column().classes("w-full gap-5"):
                    source_toggle = ui.toggle({"SEEDED": "Seeded", "PREDEFINED": "Predefined"},
                        value=controller.experiment_source).props("no-caps").mark("experiment-source")
                    with ui.column().classes("w-full gap-0") as seeded_fields:
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

                    with ui.column().classes("w-full gap-2") as predefined_fields:
                        with ui.row().classes("w-full items-center gap-2"):
                            set_select = ui.select({}, label="Predefined set").props("outlined dense").classes("flex-1")
                            refresh_sets = ui.button("Refresh sets", icon="refresh").props("outline no-caps")
                        set_status = ui.label("").classes("text-sm dahlia-muted")
                        compatibility_status = ui.label("").classes("text-sm dahlia-muted")
                        download_button = ui.button("Download for offline", icon="download").props("outline no-caps")
                        download_status = ui.label("").classes("text-sm dahlia-muted")


                    with ui.column().classes("w-full gap-0"):
                        ui.label("Select dataset").classes("dahlia-field-label")
                        dataset_select = (
                            ui.select(
                                list(DATASETS),
                                value=controller.dataset_name,
                                on_change=lambda event: controller.experiment_source == "SEEDED" and setattr(
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
                                on_change=lambda event: controller.experiment_source == "SEEDED" and setattr(
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

    def update_selection() -> None:
        if controller.experiment_source != "PREDEFINED":
            return
        selected = catalog.get(set_select.value)
        controller.predefined_selection = selected
        dataset_select.set_options(list(dict.fromkeys([*DATASETS, *([selected.dataset_name] if selected else [])])),
                                   value=selected.dataset_name if selected else None)
        fraction_select.value = str(selected.na_fraction) if selected else None
        supported = selected is not None and selected.dataset_name in DATASETS
        downloaded = {item.predefined_set_id for item in controller.predefined_cache.downloaded(controller.api_client.base_url)}
        start_button.set_enabled(supported and not downloading)
        download_button.set_enabled(supported and not downloading)
        download_button.set_text("Download again" if selected and selected.predefined_set_id in downloaded else "Download for offline")
        download_status.set_text("Downloaded for offline use." if selected and selected.predefined_set_id in downloaded else "Download this set while connected to start it later offline." if selected else "")
        compatibility_status.set_text("" if selected is None or supported else "This dataset has no method configuration in this application version.")
        if selected:
            set_status.set_text(f"Set #{selected.predefined_set_id} | Dataset: {selected.dataset_name} | NA fraction: {selected.na_fraction}")

    async def load_sets() -> None:
        nonlocal generation, wanted_id
        if downloading or not still_current() or controller.experiment_source != "PREDEFINED":
            return
        generation += 1
        request_generation = generation
        previous = set_select.value or wanted_id
        wanted_id = None
        controller.predefined_selection = None
        catalog.clear()
        set_select.set_options({}, value=None)
        set_select.disable()
        refresh_sets.disable()
        update_selection()
        set_status.set_text("Loading active sets...")
        download_button.disable()
        res = await controller.api_client.get_offline_set_catalog()
        if not still_current() or controller.experiment_source != "PREDEFINED" or request_generation != generation:
            return
        refresh_sets.enable()
        controller.is_online = not res.is_offline
        controller._update_status_badge()
        if not res.success and not res.is_offline:
            set_status.set_text(res.error or "Could not load sets.")
            return
        try:
            items = (controller.predefined_cache.downloaded(controller.api_client.base_url) if res.is_offline
                     else controller.predefined_cache.refresh(controller.api_client.base_url, res.data))
        except ValueError as exc:
            set_status.set_text(str(exc))
            return
        catalog.update({item.predefined_set_id: item for item in items})
        set_select.set_options({item.predefined_set_id: f"Set #{item.predefined_set_id} | {item.dataset_name} | {item.na_fraction}"
                                for item in items}, value=previous if previous in catalog else None)
        set_select.set_enabled(bool(items))
        set_status.set_text("Select an active set." if items else "No active sets are available.")
        if res.is_offline:
            set_status.set_text("Offline: select a downloaded set." if items else "No downloaded sets are available. Connect to the internet to download a set.")
        update_selection()

    async def download_set() -> None:
        nonlocal downloading
        selected = controller.predefined_selection
        if downloading or not still_current() or controller.experiment_source != "PREDEFINED" or selected is None:
            return
        downloading = True
        for control in (source_toggle, set_select, refresh_sets, download_button, start_button):
            control.disable()
        download_button.props("loading")
        download_status.set_text("Downloading set and dataset...")
        try:
            res = await controller.api_client.get_execution_set(selected.predefined_set_id)
            if not still_current() or controller.experiment_source != "PREDEFINED":
                return
            controller.is_online = not res.is_offline
            controller._update_status_badge()
            if not res.success:
                if res.status_code in (404, 409):
                    controller.predefined_cache.unavailable(controller.api_client.base_url, selected.predefined_set_id)
                raise ValueError("Connect to the internet to download this set." if res.is_offline else res.error or "Could not download set.")
            data = res.data
            if (not isinstance(data, dict) or data.get("predefined_set_id") != selected.predefined_set_id
                    or data.get("dataset_id") != selected.dataset_id or data.get("dataset_name") != selected.dataset_name
                    or data.get("na_fraction") != selected.na_fraction):
                raise ValueError("The server returned a different set. Refresh the catalog.")
            if data.get("catalog_id") != controller.predefined_cache.catalog_id(controller.api_client.base_url):
                controller.predefined_cache.refresh(controller.api_client.base_url, {"catalog_id": data.get("catalog_id"), "sets": []})
                raise ValueError("The database catalog changed. Refresh sets before downloading.")
            controller.predefined_cache.save(controller.api_client.base_url, data)
            download_status.set_text("Downloaded for offline use.")
        except (ValueError, KeyError, TypeError) as exc:
            if still_current():
                download_status.set_text(str(exc))
        except Exception:
            if still_current():
                download_status.set_text("The download could not be stored. Check local storage and retry.")
        finally:
            downloading = False
            if still_current():
                download_button.props(remove="loading")
                source_toggle.enable()
                set_select.set_enabled(bool(catalog))
                refresh_sets.enable()
                # Keep an error message, but update button availability.
                message = download_status.text
                update_selection()
                download_status.set_text(message)

    async def change_source() -> None:
        nonlocal generation
        generation += 1
        controller.experiment_source = source_toggle.value
        predefined = controller.experiment_source == "PREDEFINED"
        seeded_fields.set_visibility(not predefined)
        predefined_fields.set_visibility(predefined)
        dataset_select.set_enabled(not predefined)
        fraction_select.set_enabled(not predefined)
        if predefined:
            start_button.disable()
            await load_sets()
        else:
            controller.predefined_selection = None
            dataset_select.set_options(list(DATASETS), value=controller.dataset_name)
            fraction_select.value = str(controller.na_fraction)
            message = controller.set_seed_text(seed_input.value)
            seed_error.set_text(message or "")
            seed_error.set_visibility(bool(message))
            start_button.set_enabled(not message)

    def validate_seed(event: Any) -> None:
        message = controller.set_seed_text(event.value)
        seed_error.set_text(message or "")
        seed_error.set_visibility(bool(message))
        if message:
            seed_input.props("error")
            start_button.disable()
        elif controller.experiment_source == "SEEDED":
            seed_input.props(remove="error")
            start_button.enable()

    seed_input.on_value_change(validate_seed)
    set_select.on_value_change(lambda _: update_selection())
    source_toggle.on_value_change(change_source)
    refresh_sets.on_click(load_sets)
    download_button.on_click(download_set)
    download_button.disable()
    predefined_fields.set_visibility(controller.experiment_source == "PREDEFINED")
    seeded_fields.set_visibility(controller.experiment_source == "SEEDED")
    if controller.experiment_source == "PREDEFINED":
        start_button.disable()
        dataset_select.disable()
        fraction_select.disable()
        ui.timer(0.01, load_sets, once=True)
    controller.bind_setup_elements(
        source_toggle=source_toggle,
        seed_input=seed_input,
        seed_error=seed_error,
        start_button=start_button,
        loading_overlay=loading_overlay,
        controls=[
            source_toggle,
            set_select,
            refresh_sets,
            download_button,
            seed_input,
            random_button,
            dataset_select,
            fraction_select,
            projection_select,
            start_button,
        ],
    )
