"""Application state and screen navigation for the DAHLIA desktop PoC."""

from __future__ import annotations

import asyncio
import logging
import random
from concurrent.futures import Future
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
from nicegui import context, ui

from dahlia.app.components.chart import PLOTLY_CONFIG, build_experiment_figure
from dahlia.app.screens.experiment import render_experiment
from dahlia.app.screens.my_results import render_my_results
from dahlia.app.screens.profile import (
    render_login,
    render_profile,
    render_profile_view,
    render_register,
)
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
        # Navigation and auth state
        self.active_screen: str = "setup"
        self.local_experiments: list[dict] = []
        self.current_user: dict | None = None

    def _stop_monitor(self) -> None:
        if self.monitor_timer is not None:
            try:
                self.monitor_timer.deactivate()
            except Exception:
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
            LOGGER.warning("Could not update the exit guard: %s", error)

    def show_setup(
        self,
        error_message: str | None = None,
        *,
        reset_defaults: bool = False,
    ) -> None:
        """Navigate to the Setup screen, optionally resetting all form defaults."""
        if reset_defaults:
            self.seed = 0
            self.dataset_name = "iris"
            self.na_fraction = 0.1
            self.projection_name = "tsne"
        self.active_screen = "setup"
        self.experiment = None
        self.prediction_future = None
        self.algorithm_predictions = None
        self.results = None
        self._clear()
        self._set_exit_guard(False)
        with self.root:
            render_setup(self, error_message)

    def show_experiment(self) -> None:
        """Navigate to the active experiment screen and enable the exit guard."""
        self._clear()
        self._set_exit_guard(True)
        with self.root:
            render_experiment(self)

    def show_results(self) -> None:
        """Save the completed experiment locally, then navigate to Results Summary."""
        self._save_current_experiment()
        self.active_screen = "setup"
        self._clear()
        self._set_exit_guard(False)
        with self.root:
            render_results(self)

    def bind_setup_elements(self, **elements: Any) -> None:
        """Store references to Setup screen UI elements for later programmatic updates."""
        self.setup_elements = elements

    def bind_experiment_elements(self, **elements: Any) -> None:
        """Store references to Experiment screen UI elements for later programmatic updates."""
        self.experiment_elements = elements

    def set_seed_text(self, raw_value: Any) -> str | None:
        """Parse and validate a seed value from the text input.

        Updates ``self.seed`` on success.

        Returns
        -------
        str | None
            A human-readable error message, or ``None`` if the value is valid.
        """
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
        """Pick a cryptographically random seed and push it to the Setup form."""
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
        """Validate the setup form, prepare the experiment and switch screens.

        Disables the form controls and shows a loading overlay while the
        dataset and projection are computed in a background thread.
        """
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
        """Start a 250 ms timer that polls the background imputation future.

        A no-op if predictions are already available or not yet started.
        """
        if self.algorithm_predictions is not None:
            return
        if self.prediction_future is None:
            return
        self.monitor_timer = ui.timer(0.25, self.poll_prediction_future)

    def poll_prediction_future(self) -> None:
        """Check whether the background imputation future has completed.

        Called by the monitor timer.  Stops the timer on completion or error.
        """
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
        """Abort the current experiment and return to Setup with defaults reset."""
        self.show_setup(reset_defaults=True)

    # Navigation to sidebar screens

    def show_my_results(self) -> None:
        """Navigate to the My Results screen."""
        self.active_screen = "my_results"
        self._clear()
        self._set_exit_guard(False)
        with self.root:
            render_my_results(self)

    def show_profile(self) -> None:
        """Navigate to the Profile screen (landing or authenticated view)."""
        self.active_screen = "profile"
        self._clear()
        self._set_exit_guard(False)
        with self.root:
            if self.current_user is not None:
                render_profile_view(self)
            else:
                render_profile(self)

    def show_login(self, error: str | None = None) -> None:
        """Navigate to the Log-in form."""
        self.active_screen = "profile"
        self._clear()
        self._set_exit_guard(False)
        with self.root:
            render_login(self, error)

    def show_register(self, error: str | None = None) -> None:
        """Navigate to the Registration form."""
        self.active_screen = "profile"
        self._clear()
        self._set_exit_guard(False)
        with self.root:
            render_register(self, error)

    def logout(self) -> None:
        """Clear the current user session and navigate to the profile landing."""
        self.current_user = None
        self.show_profile()

    # Local data management

    def _save_current_experiment(self) -> None:
        """Append the completed experiment to the in-memory local results list.

        Stores both the metrics summary (``results`` DataFrame) and the raw
        annotator answers (``answers`` dict + ``annotation_indices``) so that
        both can be exported or synced to the database later.
        """
        if self.experiment is None or self.results is None:
            return
        self.local_experiments.append(
            {
                "date": datetime.now().strftime("%Y-%m-%d\u00a0 %H:%M"),
                "dataset": self.experiment.config.name,
                "seed": self.experiment.seed,
                "na_fraction": self.experiment.na_fraction,
                "projection": self.experiment.projection_name,
                "sync_status": "Local only",
                "results": self.results.copy(),
                # Raw annotator answers — index (int) → imputed value (float).
                "answers": {
                    int(k): float(v)
                    for k, v in self.experiment.answers.items()
                },
                # Ordered list of dataset indices that were annotated.
                "annotation_indices": [
                    int(i) for i in self.experiment.annotation_indices
                ],
            }
        )

    def delete_local_experiment(self, idx: int) -> None:
        """Remove a local experiment record by index and refresh My Results."""
        if 0 <= idx < len(self.local_experiments):
            self.local_experiments.pop(idx)
        self.show_my_results()

    def reset_current_value(self) -> None:
        """Reset slider and number input to value_min for the current step.

        Does NOT advance to the next question — the annotator can adjust and
        confirm with ``Next`` as usual.
        """
        if self.experiment is None:
            return
        self.current_prediction = self.experiment.value_min
        self._update_prediction_controls()

    def export_local_csv_metrics(
        self, experiments: list[dict] | None = None
    ) -> None:
        """Write a metrics-summary CSV (MAE/RMSE per method) to ~/Downloads.

        Parameters
        ----------
        experiments:
            Subset of records to export.  Defaults to all ``local_experiments``.
        """
        targets = experiments if experiments is not None else self.local_experiments
        if not targets:
            ui.notify("No local results to export.", type="warning")
            return
        rows = []
        for exp in targets:
            for row in exp["results"].itertuples(index=False):
                rows.append(
                    {
                        "date": exp["date"],
                        "dataset": exp["dataset"],
                        "seed": exp["seed"],
                        "na_fraction": exp["na_fraction"],
                        "projection": exp["projection"],
                        "method": str(row.Method),
                        "MAE": float(row.MAE),
                        "RMSE": float(row.RMSE),
                    }
                )

        downloads_dir = Path.home() / "Downloads"
        downloads_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filepath = downloads_dir / f"dahlia_metrics_{timestamp}.csv"
        pd.DataFrame(rows).to_csv(filepath, index=False)
        ui.notify(
            f"Exported → Downloads/dahlia_metrics_{timestamp}.csv",
            type="positive",
            timeout=6000,
        )

    def export_local_csv_answers(
        self, experiments: list[dict] | None = None
    ) -> None:
        """Write a per-point answers CSV (one row per imputed value) to ~/Downloads.

        Parameters
        ----------
        experiments:
            Subset of records to export.  Defaults to all ``local_experiments``.
        """
        targets = experiments if experiments is not None else self.local_experiments
        if not targets:
            ui.notify("No local results to export.", type="warning")
            return
        rows = []
        for exp in targets:
            answers = exp.get("answers", {})
            annotation_indices = exp.get("annotation_indices", [])
            for idx in annotation_indices:
                rows.append(
                    {
                        "date": exp["date"],
                        "dataset": exp["dataset"],
                        "seed": exp["seed"],
                        "na_fraction": exp["na_fraction"],
                        "projection": exp["projection"],
                        "annotation_index": idx,
                        "human_answer": answers.get(idx),
                    }
                )
        if not rows:
            ui.notify(
                "No answer data to export — complete an experiment first.",
                type="warning",
            )
            return

        downloads_dir = Path.home() / "Downloads"
        downloads_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filepath = downloads_dir / f"dahlia_answers_{timestamp}.csv"
        pd.DataFrame(rows).to_csv(filepath, index=False)
        ui.notify(
            f"Exported → Downloads/dahlia_answers_{timestamp}.csv",
            type="positive",
            timeout=6000,
        )

    # Mock authentication (PoC — no network layer yet)

    def mock_login(self, email: str, password: str) -> str | None:
        """Validate credentials and set current_user (PoC stub — no network).

        Returns an error message string on failure, or ``None`` on success.
        """
        email = email.strip()
        if not email:
            return "Email is required."
        if "@" not in email or "." not in email.split("@")[-1]:
            return "Enter a valid email address."
        if not password.strip():
            return "Password is required."
        self.current_user = {
            "email": email,
            "username": email.split("@")[0],
            "role": "User",
            "affiliated": False,
            "index_no": None,
        }
        return None

    def mock_register(
        self,
        email: str,
        username: str,
        password: str,
        affiliated: bool,
        index_no: str,
        agreed: bool,
    ) -> str | None:
        """Validate the registration form (PoC stub — no network request).

        Returns an error message string on failure, or ``None`` on success.
        """
        email = email.strip()
        username = username.strip()
        if not email:
            return "Email is required."
        if "@" not in email or "." not in email.split("@")[-1]:
            return "Enter a valid email address."
        if not username:
            return "Username is required."
        if not password.strip():
            return "Password is required."
        if affiliated:
            idx = index_no.strip()
            if not idx:
                return "Student index number is required."
            if not idx.isdigit():
                return "Student index number must contain digits only."
        if not agreed:
            return "You must agree to the data processing terms."
        return None
