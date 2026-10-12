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

from dahlia.core.api_client import ApiClient
from dahlia.app.components.chart import PLOTLY_CONFIG, build_experiment_figure
from dahlia.app.screens.experiment import render_experiment
from dahlia.app.screens.my_results import render_my_results
from dahlia.app.screens.admin import render_admin
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
    LocalStorage,
    PreparedExperiment,
    calculate_results,
    prepare_experiment,
    snap_value,
    start_algorithm_predictions,
)
from dahlia.services.experiment import build_storage_details, precision_digits

LOGGER = logging.getLogger(__name__)


class AppController:
    """Own all ephemeral application state; nothing is persisted to disk."""

    def __init__(self, root: Any, storage: LocalStorage | None = None) -> None:
        try:
            self._client = context.client
        except Exception:
            self._client = None
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
        self._saved_experiment_uid: str | None = None

        self.setup_elements: dict[str, Any] = {}
        self.experiment_elements: dict[str, Any] = {}
        # Navigation and persistent storage state
        self.active_screen: str = "setup"
        self.storage: LocalStorage = storage or LocalStorage()
        self.local_experiments: list[dict] = self.storage.get_experiments()
        self.current_user: dict | None = None
        self.api_client: ApiClient = ApiClient()
        self.is_online: bool = False
        self._sync_in_progress = False
        self.last_sync_error: str | None = None

        if self._client is not None:
            ui.timer(0.05, self.startup_check, once=True)

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

        if self._client is not None and getattr(self._client, "has_socket_connection", False):
            try:
                self._client.run_javascript(javascript)
            except Exception as error:
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
        self._saved_experiment_uid = None
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
        self._saved_experiment_uid = None
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

    def show_admin(self) -> None:
        """Navigate to the Admin Panel screen (DEVELOPER role only)."""
        if self.current_user is None or self.current_user.get("role") != "DEVELOPER":
            self.show_profile()
            return
        self.active_screen = "admin"
        self._clear()
        self._set_exit_guard(False)
        with self.root:
            render_admin(self)

    async def logout(self) -> None:
        """Clear session on backend, delete keyring token, and navigate to profile."""
        await self.api_client.logout()
        self.current_user = None
        self.show_profile()

    # Local data management

    def _save_current_experiment(self) -> None:
        """Persist completed experiment to SQLite buffer with sync_status 'Local only'.

        Store metrics, human answers, every removed value and all baseline
        predictions once per completed experiment. The original dataframe is
        not persisted. A failed write leaves the experiment available to retry.
        """
        if self.experiment is None or self.results is None:
            return
        if self._saved_experiment_uid is not None:
            return
        if self.algorithm_predictions is None:
            raise ValueError("Baseline predictions must be ready before saving.")
        completed_data = build_storage_details(self.experiment, self.algorithm_predictions)

        user_id = self.current_user.get("user_id") if self.current_user else None
        answers = {int(k): float(v) for k, v in self.experiment.answers.items()}
        annotation_indices = [int(i) for i in self.experiment.annotation_indices]

        self._saved_experiment_uid = self.storage.save_experiment(
            dataset_name=self.experiment.config.name,
            seed=self.experiment.seed,
            na_fraction=self.experiment.na_fraction,
            projection=self.experiment.projection_name,
            results_df=self.results.copy(),
            answers=answers,
            annotation_indices=annotation_indices,
            user_id=user_id,
            sync_status="Local only",
            completed_data=completed_data,
        )
        self.local_experiments = self.storage.get_experiments()

    def delete_local_experiment(self, idx: int) -> None:
        """Remove a local experiment record from SQLite and refresh My Results."""
        if 0 <= idx < len(self.local_experiments):
            exp = self.local_experiments[idx]
            uid = exp.get("experiment_uid")
            if uid:
                self.storage.delete_experiment(uid)
            self.local_experiments = self.storage.get_experiments()
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

    # Authentication and session management

    def _set_user_from_profile(self, data: dict[str, Any]) -> None:
        """Map backend user profile dictionary to internal current_user dict."""
        self.current_user = {
            "user_id": data.get("user_id"),
            "email": str(data.get("email", "")),
            "username": str(data.get("display_name") or data.get("email", "").split("@")[0]),
            "role": str(data.get("role_code", "USER")),
            "affiliated": bool(data.get("is_pw_affiliated", False)),
            "index_no": data.get("student_id_number"),
            "is_email_verified": bool(data.get("is_email_verified", False)),
        }
        # Anonymous records stay anonymous until explicitly assigned in My Results.

    def _update_status_badge(self) -> None:
        """Update connection status badge in sidebar if rendered."""
        badge = getattr(self, "_status_badge", None)
        if badge is not None:
            try:
                badge.content = (
                    '<span class="dahlia-status-badge dahlia-status-online">Online</span>'
                    if self.is_online
                    else '<span class="dahlia-status-badge dahlia-status-offline">Offline mode</span>'
                )
            except Exception:
                pass

    async def startup_check(self) -> None:
        """Verify API connectivity and attempt silent auto-login via stored refresh token."""
        health = await self.api_client.check_health()
        self.is_online = health.success
        self._update_status_badge()

        if self.is_online and self.current_user is None:
            res = await self.api_client.auto_login()
            if res.success and isinstance(res.data, dict):
                self._set_user_from_profile(res.data)
                LOGGER.info(
                    "Silent auto-login succeeded for <%s> (role=%s)",
                    self.current_user["email"],
                    self.current_user["role"],
                )
                if self.active_screen == "profile":
                    self.show_profile()

    async def do_login(self, email: str, password: str) -> str | None:
        """Authenticate user against the backend API.

        Returns an error message string on failure, or ``None`` on success.
        """
        email = email.strip()
        if not email:
            return "Email is required."
        if "@" not in email or "." not in email.split("@")[-1]:
            return "Enter a valid email address."
        if not password:
            return "Password is required."

        result = await self.api_client.login(email, password)
        if result.is_offline:
            self.is_online = False
            return "Cannot connect to server. Running in offline mode."

        if not result.success:
            self.is_online = True
            return result.error or "Login failed."

        self.is_online = True
        me_res = await self.api_client.get_me()
        if me_res.success and isinstance(me_res.data, dict):
            self._set_user_from_profile(me_res.data)
        else:
            role = self.api_client.get_current_role() or "USER"
            claims = (
                self.api_client.decode_token_payload(self.api_client.access_token)
                if self.api_client.access_token
                else None
            )
            user_id = int(claims["sub"]) if claims and "sub" in claims else None
            self.current_user = {
                "user_id": user_id,
                "email": email,
                "username": email.split("@")[0],
                "role": role,
                "affiliated": False,
                "index_no": None,
                "is_email_verified": False,
            }
        return None

    def get_unassigned_experiment_uids(self) -> list[str]:
        return [record["experiment_uid"] for record in self.storage.get_unsynced_experiments()
                if record.get("user_id") is None]

    def assign_unassigned_experiments(self, expected_user_id: int, experiment_uids: list[str]) -> int:
        """Apply an assignment confirmation only if the account has not changed."""
        if self.current_user is None or self.current_user.get("user_id") != expected_user_id:
            return 0
        updated = self.storage.assign_experiments(expected_user_id, experiment_uids)
        self.local_experiments = self.storage.get_experiments()
        return updated

    def get_upload_candidates(self) -> list[dict]:
        if self.current_user is None or self.current_user.get("user_id") is None:
            return []
        owner = self.current_user["user_id"]
        return [record for record in self.storage.get_unsynced_experiments()
                if record.get("user_id") == owner
                and record.get("payload", {}).get("payload_schema_version") == 2]

    async def sync_local_experiments(
        self, *, experiment_uids: list[str] | None = None, expected_user_id: int | None = None,
    ) -> tuple[int, int]:
        """Upload unsynced local experiments to the central backend database.

        Returns
        -------
        tuple[int, int]
            (synced_count, failed_count)
        """
        if not self.is_online or self.current_user is None or self._sync_in_progress:
            return 0, 0
        owner = self.current_user.get("user_id")
        if owner is None or (expected_user_id is not None and owner != expected_user_id):
            return 0, 0
        unsynced = self.get_upload_candidates()
        if experiment_uids is not None:
            confirmed = set(experiment_uids)
            unsynced = [record for record in unsynced if record["experiment_uid"] in confirmed]
        if not unsynced:
            return 0, 0

        self._sync_in_progress = True
        self.last_sync_error = None
        synced_count = 0
        failed_count = 0
        try:
            for exp in unsynced:
                if self.current_user is None or self.current_user.get("user_id") != owner:
                    break
                uid = exp["experiment_uid"]
                payload = dict(exp.get("payload", {}))
                payload["experiment_uid"] = uid
                payload["user_id"] = owner
                self.storage.update_sync_status(uid, "Sync pending")
                try:
                    res = await self.api_client.sync_experiment(payload)
                    acknowledged = (
                        res.success and res.status_code in (200, 201)
                        and isinstance(res.data, dict)
                        and res.data.get("status") in ("synced", "already_synced")
                        and res.data.get("experiment_uid") == uid
                    )
                    if res.is_offline:
                        self.is_online = False
                    error = res.error or "The server did not confirm this experiment."
                except Exception:
                    LOGGER.exception("Experiment upload failed")
                    acknowledged = False
                    error = "Connection failed; retry the upload."
                if acknowledged:
                    self.storage.update_sync_status(uid, "Synced")
                    synced_count += 1
                else:
                    self.storage.update_sync_status(uid, "Sync failed")
                    self.last_sync_error = error
                    failed_count += 1
                if not self.is_online:
                    break
        finally:
            self._sync_in_progress = False
            self.local_experiments = self.storage.get_experiments()
        return synced_count, failed_count

    async def do_register(
        self,
        email: str,
        username: str,
        password: str,
        affiliated: bool,
        index_no: str,
        agreed: bool,
    ) -> str | None:
        """Register a new user account via the backend API.

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
        if not password:
            return "Password is required."
        if len(password) < 8:
            return "Password must be at least 8 characters long."
        if affiliated:
            idx = index_no.strip()
            if not idx:
                return "Student index number is required."
            if not (idx.isdigit() and len(idx) == 6):
                return "Student index number must be exactly 6 digits."
        else:
            idx = ""
        if not agreed:
            return "You must agree to the data processing terms."

        result = await self.api_client.register(
            email=email,
            password=password,
            display_name=username,
            is_pw_affiliated=affiliated,
            student_id_number=idx if affiliated else None,
            consent_given=agreed,
        )
        if result.is_offline:
            self.is_online = False
            return "Cannot connect to server. Registration requires an internet connection."

        if not result.success:
            self.is_online = True
            return result.error or "Registration failed."

        self.is_online = True
        return None

    async def request_role(
        self, requested_role: str = "RESEARCHER"
    ) -> tuple[bool, str]:
        """Submit a role-upgrade request for the authenticated user.

        Parameters
        ----------
        requested_role:
            Role code to request (``"RESEARCHER"`` or ``"USER_PLUS"``).

        Returns
        -------
        tuple[bool, str]
            Tuple of (success_flag, feedback_message).
        """
        if self.current_user is None:
            return False, "You must be logged in to request a higher role."

        result = await self.api_client.request_role(requested_role)
        if result.is_offline:
            self.is_online = False
            return False, "Cannot connect to server. Running in offline mode."

        if not result.success:
            self.is_online = True
            return False, result.error or "Could not submit role request."

        self.is_online = True
        msg = "Role upgrade request submitted successfully."
        if isinstance(result.data, dict) and "message" in result.data:
            msg = str(result.data["message"])
        return True, msg

    def mock_login(self, email: str, password: str) -> str | None:
        """Validate credentials and set current_user (local fallback)."""
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
            "role": "USER",
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
        """Validate the registration form (local fallback)."""
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

