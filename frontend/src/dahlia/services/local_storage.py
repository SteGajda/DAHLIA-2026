"""Offline-first local SQLite storage for completed experiment records.

Provides persistent storage in the user application data directory
(%APPDATA%/DAHLIA on Windows) so that experiments survive app restarts,
remain available offline, and can be queued for database synchronisation.
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

LOGGER = logging.getLogger(__name__)


def get_default_db_path() -> Path:
    """Return default platform-specific path for dahlia_local.db.

    Windows: %APPDATA%/DAHLIA/dahlia_local.db
    macOS / Linux: ~/.local/share/DAHLIA/dahlia_local.db
    """
    appdata = os.getenv("APPDATA")
    if appdata:
        base_dir = Path(appdata) / "DAHLIA"
    else:
        base_dir = Path.home() / ".local" / "share" / "DAHLIA"
    return base_dir / "dahlia_local.db"


class LocalStorage:
    """SQLite manager for buffering and querying completed experiments offline."""

    def __init__(self, db_path: Path | str | None = None) -> None:
        """Initialise local SQLite connection and ensure schema exists.

        Parameters
        ----------
        db_path:
            Path to SQLite database file, or ``":memory:"`` for isolated tests.
            Defaults to ``%APPDATA%/DAHLIA/dahlia_local.db``.
        """
        if db_path is None:
            self.db_path = get_default_db_path()
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            self._connection_target = str(self.db_path)
        elif str(db_path) == ":memory:":
            self.db_path = Path(":memory:")
            self._connection_target = ":memory:"
            # In-memory database requires persistent connection across calls
            self._in_memory_conn: sqlite3.Connection | None = sqlite3.connect(":memory:")
        else:
            self.db_path = Path(db_path)
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            self._connection_target = str(self.db_path)
            self._in_memory_conn = None

        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        """Create or return an active SQLite connection."""
        if self._connection_target == ":memory:":
            assert self._in_memory_conn is not None
            self._in_memory_conn.row_factory = sqlite3.Row
            return self._in_memory_conn
        conn = sqlite3.connect(self._connection_target)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        """Create local_experiments table if it does not exist."""
        conn = self._get_connection()
        try:
            with conn:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS local_experiments (
                        experiment_uid TEXT PRIMARY KEY,
                        created_at TEXT NOT NULL,
                        dataset_name TEXT NOT NULL,
                        seed INTEGER NOT NULL,
                        na_fraction REAL NOT NULL,
                        projection TEXT NOT NULL,
                        user_id INTEGER,
                        sync_status TEXT NOT NULL DEFAULT 'Local only',
                        payload_json TEXT NOT NULL
                    )
                    """
                )
        finally:
            if self._connection_target != ":memory:":
                conn.close()

    def save_experiment(
        self,
        *,
        dataset_name: str,
        seed: int,
        na_fraction: float,
        projection: str,
        results_df: pd.DataFrame,
        answers: dict[int, float],
        annotation_indices: list[int],
        user_id: int | None = None,
        created_at: str | None = None,
        sync_status: str = "Local only",
        experiment_uid: str | None = None,
        completed_data: dict[str, Any] | None = None,
    ) -> str:
        """Persist a completed experiment record to SQLite.

        ``completed_data`` is produced by ``build_storage_details`` and makes
        the payload version 2. Calls using the legacy arguments remain version
        1; they cannot recover truth or predictions absent from older records.

        Returns
        -------
        str
            The generated or supplied ``experiment_uid`` (UUID v4 string).
        """
        uid = experiment_uid or str(uuid.uuid4())
        ts = created_at or datetime.now(timezone.utc).isoformat()

        # Build serialisable payload
        results_records = results_df.to_dict(orient="records")
        payload = {
            "payload_schema_version": 1,
            "experiment_uid": uid,
            "created_at": ts,
            "dataset_name": dataset_name,
            "seed": seed,
            "na_fraction": na_fraction,
            "projection": projection,
            "user_id": user_id,
            "answers": {str(k): float(v) for k, v in answers.items()},
            "annotation_indices": [int(i) for i in annotation_indices],
            "metrics": results_records,
        }
        if completed_data is not None:
            expected_fields = {
                "app_version", "dataset_config", "removed_indices",
                "true_values", "algorithm_predictions",
            }
            if set(completed_data) != expected_fields:
                raise ValueError("Completed experiment data has unexpected or missing fields.")
            payload.update(completed_data)
            payload["payload_schema_version"] = 2
        # Reject NaN/Infinity rather than persisting non-standard JSON.
        payload_str = json.dumps(payload, allow_nan=False)

        conn = self._get_connection()
        try:
            with conn:
                conn.execute(
                    """
                    INSERT INTO local_experiments (
                        experiment_uid,
                        created_at,
                        dataset_name,
                        seed,
                        na_fraction,
                        projection,
                        user_id,
                        sync_status,
                        payload_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        uid,
                        ts,
                        dataset_name,
                        int(seed),
                        float(na_fraction),
                        projection,
                        user_id,
                        sync_status,
                        payload_str,
                    ),
                )
            return uid
        finally:
            if self._connection_target != ":memory:":
                conn.close()

    def get_experiments(self) -> list[dict[str, Any]]:
        """Retrieve all local experiments ordered newest first.

        Deserialises payload_json and converts stored metrics back into
        a pandas DataFrame to match AppController requirements.
        """
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT
                    experiment_uid,
                    created_at,
                    dataset_name,
                    seed,
                    na_fraction,
                    projection,
                    user_id,
                    sync_status,
                    payload_json
                FROM local_experiments
                ORDER BY created_at DESC
                """
            )
            rows = cursor.fetchall()
            experiments: list[dict[str, Any]] = []

            for row in rows:
                try:
                    payload = json.loads(row["payload_json"] if isinstance(row, sqlite3.Row) else row[8])
                except Exception:
                    payload = {}

                metrics_records = payload.get("metrics", [])
                # Records from before versioned payloads remain readable.
                payload.setdefault("payload_schema_version", 1)
                results_df = pd.DataFrame(metrics_records) if metrics_records else pd.DataFrame()

                # Parse display date
                raw_ts = row["created_at"] if isinstance(row, sqlite3.Row) else row[1]
                display_date = raw_ts[:16].replace("T", " ")

                raw_answers = payload.get("answers", {})
                answers_dict = {int(k): float(v) for k, v in raw_answers.items()}

                uid_val = row["user_id"] if isinstance(row, sqlite3.Row) else row[6]
                payload["user_id"] = uid_val

                experiments.append(
                    {
                        "experiment_uid": row["experiment_uid"] if isinstance(row, sqlite3.Row) else row[0],
                        "date": display_date,
                        "created_at": raw_ts,
                        "dataset": row["dataset_name"] if isinstance(row, sqlite3.Row) else row[2],
                        "seed": row["seed"] if isinstance(row, sqlite3.Row) else row[3],
                        "na_fraction": row["na_fraction"] if isinstance(row, sqlite3.Row) else row[4],
                        "projection": row["projection"] if isinstance(row, sqlite3.Row) else row[5],
                        "user_id": uid_val,
                        "sync_status": row["sync_status"] if isinstance(row, sqlite3.Row) else row[7],
                        "results": results_df,
                        "answers": answers_dict,
                        "annotation_indices": payload.get("annotation_indices", []),
                        "payload": payload,
                    }
                )
            return experiments
        finally:
            if self._connection_target != ":memory:":
                conn.close()

    def get_unsynced_experiments(self) -> list[dict[str, Any]]:
        """Retrieve local experiments whose sync_status is not 'Synced'."""
        return [e for e in self.get_experiments() if e.get("sync_status") != "Synced"]

    def delete_experiment(self, experiment_uid: str) -> bool:
        """Delete an experiment record by UUID."""
        conn = self._get_connection()
        try:
            with conn:
                cursor = conn.execute(
                    "DELETE FROM local_experiments WHERE experiment_uid = ?",
                    (experiment_uid,),
                )
                return cursor.rowcount > 0
        finally:
            if self._connection_target != ":memory:":
                conn.close()

    def update_sync_status(self, experiment_uid: str, sync_status: str) -> bool:
        """Update synchronization status of an experiment record."""
        conn = self._get_connection()
        try:
            with conn:
                cursor = conn.execute(
                    "UPDATE local_experiments SET sync_status = ? WHERE experiment_uid = ?",
                    (sync_status, experiment_uid),
                )
                return cursor.rowcount > 0
        finally:
            if self._connection_target != ":memory:":
                conn.close()

    def assign_user_to_unassigned(self, user_id: int) -> int:
        """Assign user_id to records created while offline without an active session."""
        conn = self._get_connection()
        try:
            with conn:
                cursor = conn.execute(
                    "UPDATE local_experiments SET user_id = ? WHERE user_id IS NULL",
                    (user_id,),
                )
                return cursor.rowcount
        finally:
            if self._connection_target != ":memory:":
                conn.close()

    def assign_experiments(self, user_id: int, experiment_uids: list[str]) -> int:
        """Assign only the anonymous, unsynced records explicitly confirmed by the user."""
        if isinstance(user_id, bool) or not isinstance(user_id, int) or user_id <= 0:
            raise ValueError("A valid account ID is required.")
        conn = self._get_connection()
        updated = 0
        try:
            with conn:
                for uid in dict.fromkeys(experiment_uids):
                    row = conn.execute(
                        "SELECT payload_json FROM local_experiments "
                        "WHERE experiment_uid = ? AND user_id IS NULL AND sync_status != 'Synced'",
                        (uid,),
                    ).fetchone()
                    if row is None:
                        continue
                    payload = json.loads(row["payload_json"])
                    payload["user_id"] = user_id
                    result = conn.execute(
                        "UPDATE local_experiments SET user_id = ?, payload_json = ? "
                        "WHERE experiment_uid = ? AND user_id IS NULL AND sync_status != 'Synced'",
                        (user_id, json.dumps(payload, allow_nan=False), uid),
                    )
                    updated += result.rowcount
            return updated
        finally:
            if self._connection_target != ":memory:":
                conn.close()

