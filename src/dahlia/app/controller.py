"""Application state and transitions between the three MVP screens."""

from __future__ import annotations

import asyncio
import logging
import random
from concurrent.futures import Future
from typing import Any

import pandas as pd
from nicegui import context, ui

from dahlia.app.components.chart import PLOTLY_CONFIG, build_experiment_figure
from dahlia.app.screens.experiment import render_experiment
from dahlia.app.screens.results import render_results
from dahlia.app.screens.setup import render_setup
from dahlia.services import (
    DATASETS,
    MAX_SEED,
    PreparedExperiment,
    calculate_results,
    prepare_experiment,
    snap_value,
    start_algorithm_predictions,
)
from dahlia.services.experiment import precision_digits

LOGGER = logging.getLogger(__name__)


class AppController:
    """Own all ephemeral application state; nothing is persisted to disk."""

    def __init__(self, root: Any) -> None:
        self._client = context.client
        self.root = root
        self.monitor_timer: Any | None = None
        self._syncing_prediction = False

        self.seed = 0
        self.dataset_name = "iris"
        self.na_fraction = 0.1
        self.projection_name = "tsne"

        self.experiment: PreparedExperiment | None = None
        self.prediction_future: Future | None = None
        self.algorithm_predictions: dict[str, pd.Series] | None = None
        self.current_prediction = 0.0
        self.results: pd.DataFrame | None = None

        self.setup_elements: dict[str, Any] = {}
        self.experiment_elements: dict[str, Any] = {}

    def _stop_monitor(self) -> None:
        if self.monitor_timer is not None:
            try:
                self.monitor_timer.deactivate()
            except Exception:  # pragma: no cover - defensive UI cleanup
                LOGGER.debug("Could not deactivate timer", exc_info=True)
            self.monitor_timer = None

    def _clear(self) -> None:
        self._stop_monitor()
        self.root.clear()

    def _set_exit_guard(self, enabled: bool) -> None:
        """Enable or disable the warning shown when the app window is closed."""

        if enabled:
            javascript = """
                window.onbeforeunload = function (event) {
                    event.preventDefault();
                    event.returnValue = '';
                    return '';
                };
            """
        else:
            javascript = """
                window.onbeforeunload = null;
            """

        try:
            self._client.run_javascript(javascript)
        except RuntimeError as error:
            print(f"Could not update the exit guard: {error}")

    def show_setup(
        self,
        error_message: str | None = None,
        *,
        reset_defaults: bool = False,
    ) -> None:
        if reset_defaults:
            self.seed = 0
            self.dataset_name = "iris"
            self.na_fraction = 0.1
            self.projection_name = "tsne"
        self.experiment = None
        self.prediction_future = None
        self.algorithm_predictions = None
        self.results = None
        self._clear()
        self._set_exit_guard(False)
        with self.root:
            render_setup(self, error_message)

    def show_experiment(self) -> None:
        self._clear()
        self._set_exit_guard(True)
        with self.root:
            render_experiment(self)

    def show_results(self) -> None:
        self._clear()
        self._set_exit_guard(False)
        with self.root:
            render_results(self)

    def bind_setup_elements(self, **elements: Any) -> None:
        self.setup_elements = elements

    def bind_experiment_elements(self, **elements: Any) -> None:
        self.experiment_elements = elements

    def set_seed_text(self, raw_value: Any) -> str | None:
        text = "" if raw_value is None else str(raw_value).strip()
        if not text:
            return "Seed is required."
        try:
            value = int(text)
        except (TypeError, ValueError):
            return "Seed must be an integer."
        if str(value) != text and text not in {f"+{value}", f"0{value}"}:
            # Reject decimal representations such as 1.5 while still allowing the
            # browser to normalize ordinary integer text.
            try:
                if float(text) != value:
                    return "Seed must be an integer."
            except ValueError:
                return "Seed must be an integer."
        if value < 0 or value > MAX_SEED:
            return f"Seed must be between 0 and {MAX_SEED}."
        self.seed = value
        return None

    def generate_random_seed(self) -> None:
        self.seed = random.SystemRandom().randint(0, MAX_SEED)
        seed_input = self.setup_elements.get("seed_input")
        if seed_input is not None:
            seed_input.value = str(self.seed)
            seed_input.update()
        seed_error = self.setup_elements.get("seed_error")
        if seed_error is not None:
            seed_error.set_visibility(False)
        start_button = self.setup_elements.get("start_button")
        if start_button is not None:
            start_button.enable()

    async def start_experiment(self) -> None:
        message = self.set_seed_text(
            self.setup_elements.get("seed_input").value
            if self.setup_elements.get("seed_input") is not None
            else self.seed
        )
        if message:
            return

        controls = self.setup_elements.get("controls", [])
        overlay = self.setup_elements.get("loading_overlay")
        for control in controls:
            control.disable()
        if overlay is not None:
            overlay.set_visibility(True)
        self._set_exit_guard(True)
        await asyncio.sleep(0)

        try:
            experiment = await asyncio.to_thread(
                prepare_experiment,
                DATASETS[self.dataset_name],
                self.seed,
                self.na_fraction,
                self.projection_name,
            )
            prediction_future = start_algorithm_predictions(experiment)
        except Exception as exc:
            LOGGER.exception("Experiment preparation failed")
            self.show_setup(
                f"The experiment could not be prepared. {exc}",
                reset_defaults=False,
            )
            return

        self.experiment = experiment
        self.prediction_future = prediction_future
        self.algorithm_predictions = None
        self.current_prediction = experiment.value_min
        self.results = None
        self.show_experiment()

    def _chart_payload(self) -> dict:
        assert self.experiment is not None
        payload = build_experiment_figure(
            self.experiment,
            self.current_prediction,
        ).to_plotly_json()
        payload["config"] = PLOTLY_CONFIG
        return payload

    def _update_prediction_controls(self) -> None:
        if self._syncing_prediction or self.experiment is None:
            return
        self._syncing_prediction = True
        try:
            digits = precision_digits(self.experiment.config.precision)
            slider = self.experiment_elements.get("slider")
            if slider is not None:
                slider.value = self.current_prediction
                slider.update()
            number_input = self.experiment_elements.get("number_input")
            if number_input is not None:
                number_input.value = f"{self.current_prediction:.{digits}f}"
                number_input.update()
            value_text = self.experiment_elements.get("value_text")
            if value_text is not None:
                value_text.set_content(
                    f"{self.experiment.config.incomplete_column} = "
                    f"<b>{self.current_prediction:.{digits}f}</b>"
                )
            chart = self.experiment_elements.get("chart")
            if chart is not None:
                chart.update_figure(self._chart_payload())
        finally:
            self._syncing_prediction = False

    def _set_prediction(self, value: float) -> None:
        assert self.experiment is not None
        self.current_prediction = snap_value(
            value,
            self.experiment.value_min,
            self.experiment.value_max,
            self.experiment.config.precision,
        )
        self._update_prediction_controls()

    def prediction_from_slider(self, event: Any) -> None:
        if self._syncing_prediction:
            return
        try:
            self._set_prediction(float(event.value))
        except (TypeError, ValueError):
            return

    def prediction_from_input(self, event: Any) -> None:
        if self._syncing_prediction:
            return
        raw_value = event.value
        if raw_value is None or str(raw_value).strip() == "":
            return
        try:
            self._set_prediction(float(raw_value))
        except (TypeError, ValueError):
            return

    def restore_prediction_input(self) -> None:
        self._update_prediction_controls()

    async def confirm_current_prediction(self) -> None:
        if self.experiment is None:
            return
        next_button = self.experiment_elements.get("next_button")
        if next_button is not None:
            next_button.disable()

        index = self.experiment.current_index
        self.experiment.answers[index] = self.current_prediction

        if not self.experiment.is_complete:
            self.current_prediction = self.experiment.value_min
            self.show_experiment()
            return

        await self._finish_experiment()

    async def _finish_experiment(self) -> None:
        result_overlay = self.experiment_elements.get("result_overlay")
        if result_overlay is not None:
            result_overlay.set_visibility(True)
        self._stop_monitor()
        await asyncio.sleep(0)

        try:
            if self.algorithm_predictions is None:
                if self.prediction_future is None:
                    raise RuntimeError("Baseline calculations were not started.")
                self.algorithm_predictions = await asyncio.wrap_future(
                    self.prediction_future
                )
            assert self.experiment is not None
            self.results = await asyncio.to_thread(
                calculate_results,
                self.experiment,
                self.algorithm_predictions,
            )
        except Exception as exc:
            LOGGER.exception("Result calculation failed")
            self.show_setup(
                f"The experiment was interrupted because a method failed. {exc}",
                reset_defaults=False,
            )
            return

        self.show_results()

    def start_prediction_monitor(self) -> None:
        if self.algorithm_predictions is not None:
            return
        if self.prediction_future is None:
            return
        self.monitor_timer = ui.timer(0.25, self.poll_prediction_future)

    def poll_prediction_future(self) -> None:
        if self.prediction_future is None or not self.prediction_future.done():
            return
        try:
            self.algorithm_predictions = self.prediction_future.result()
        except Exception as exc:
            LOGGER.exception("Background imputation failed")
            self.show_setup(
                f"The experiment was interrupted because a method failed. {exc}",
                reset_defaults=False,
            )
            return
        self._stop_monitor()

    def restart_experiment(self) -> None:
        self.show_setup(reset_defaults=True)

    def start_new_experiment(self) -> None:
        self.show_setup(reset_defaults=True)
