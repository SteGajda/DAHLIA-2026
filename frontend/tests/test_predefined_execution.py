"""Migration durability, deterministic execution, local persistence and start flow."""

import asyncio
import base64
import hashlib
import json
import sqlite3
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import numpy as np
import pandas as pd
import pytest

from dahlia.app.controller import AppController
from dahlia.core.api_client import ApiResult
from dahlia.services.config import IRIS_CONFIG
from dahlia.services.data import resolve_project_path
from dahlia.services.experiment import prepare_experiment, calculate_algorithm_predictions, calculate_results, build_storage_details
from dahlia.services.local_storage import LocalStorage
from dahlia.services.predefined_cache import PredefinedCache
from dahlia.services.predefined_sets import CatalogSet


def bundle():
    content = resolve_project_path(IRIS_CONFIG.path).read_bytes()
    return dict(predefined_set_id=8, dataset_id=1, dataset_name="iris", na_fraction=0.2, is_active=True,
        removed_indices=list(range(30)), annotation_indices=list(range(29, 14, -1)), row_count=150,
        csv_base64=base64.b64encode(content).decode(), csv_sha256=hashlib.sha256(content).hexdigest(),
        imputed_column=IRIS_CONFIG.incomplete_column, target_column=IRIS_CONFIG.target_column,
        reference_columns=list(IRIS_CONFIG.reference_columns), categorical_columns=list(IRIS_CONFIG.categorical_columns), precision=0.1)


def legacy(connection):
    connection.row_factory = sqlite3.Row
    connection.execute("""CREATE TABLE local_experiments (
        experiment_uid TEXT PRIMARY KEY, created_at TEXT NOT NULL, dataset_name TEXT NOT NULL,
        seed INTEGER NOT NULL, na_fraction REAL NOT NULL, projection TEXT NOT NULL,
        user_id INTEGER, sync_status TEXT NOT NULL DEFAULT 'Local only', payload_json TEXT NOT NULL)""")
    connection.execute("INSERT INTO local_experiments VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ("legacy-uuid", "2026-10-01T12:00:00Z", "iris", 42, 0.2, "pca", 7, "Synced", '{"metrics": [], "custom": "kept"}'))
    connection.commit()


def test_file_migration_preserves_original_bytes_and_creates_one_backup(tmp_path):
    path = tmp_path / "local.db"
    with sqlite3.connect(path) as conn:
        legacy(conn)
        original = tuple(conn.execute("SELECT * FROM local_experiments").fetchone())
    storage = LocalStorage(path)
    saved = storage.get_experiments()[0]
    assert saved["seed"] == 42 and saved["source_type"] == "SEEDED" and saved["sync_status"] == "Synced"
    assert saved["user_id"] == 7 and saved["experiment_uid"] == "legacy-uuid"
    with sqlite3.connect(path) as conn:
        assert conn.execute("SELECT * FROM local_experiments").fetchone()[:9] == original
    backups = list(tmp_path.glob("*.bak"))
    assert len(backups) == 1
    with sqlite3.connect(backups[0]) as conn:
        assert conn.execute("SELECT * FROM local_experiments").fetchone() == original
    LocalStorage(path)
    assert len(list(tmp_path.glob("*.bak"))) == 1


def test_failed_migration_restores_old_table_even_after_drop():
    conn = sqlite3.connect(":memory:")
    legacy(conn)
    class FailingConnection:
        def execute(self, sql):
            if sql.startswith("ALTER TABLE"):
                raise sqlite3.OperationalError("injected rename failure")
            return conn.execute(sql)
        def __enter__(self):
            return conn.__enter__()
        def __exit__(self, *args):
            return conn.__exit__(*args)
    storage = LocalStorage.__new__(LocalStorage)
    storage._connection_target = ":memory:"
    storage._get_connection = lambda: FailingConnection()
    with pytest.raises(sqlite3.OperationalError):
        storage._init_db()
    assert conn.execute("SELECT seed FROM local_experiments").fetchone()[0] == 42
    assert "source_type" not in {row["name"] for row in conn.execute("PRAGMA table_info(local_experiments)")}
    conn.close()


def test_predefined_never_samples_and_repeats_projection_methods_and_storage():
    data = bundle()
    with patch("dahlia.services.experiment.ExperimentSampler", side_effect=AssertionError("Must not sample")):
        first = prepare_experiment(IRIS_CONFIG, 999, 0.2, "pca", predefined_bundle=data)
        second = prepare_experiment(IRIS_CONFIG, 123, 0.2, "pca", predefined_bundle=data)
    assert first.seed == second.seed == 0
    assert first.source_type == "PREDEFINED" and first.predefined_set_id == 8
    assert first.annotation_indices.tolist() == data["annotation_indices"]
    assert first.incomplete.index[first.incomplete[IRIS_CONFIG.incomplete_column].isna()].tolist() == data["removed_indices"]
    np.testing.assert_allclose(first.coordinates, second.coordinates)
    predictions = calculate_algorithm_predictions(first)
    repeated = calculate_algorithm_predictions(second)
    for method in predictions:
        np.testing.assert_allclose(predictions[method], repeated[method])
    first.answers = {int(i): float(first.original.loc[i, IRIS_CONFIG.incomplete_column]) for i in first.annotation_indices}
    results = calculate_results(first, predictions)
    storage = LocalStorage(":memory:")
    ids = [storage.save_experiment(dataset_name="iris", seed=None, source_type="PREDEFINED", predefined_set_id=8,
        na_fraction=0.2, projection="pca", results_df=results, answers=first.answers,
        annotation_indices=first.annotation_indices.tolist(), completed_data=build_storage_details(first, predictions)) for _ in range(2)]
    assert ids[0] != ids[1]
    for saved in storage.get_experiments():
        assert saved["seed"] is None and saved["predefined_set_id"] == 8
        assert saved["payload"]["source_type"] == "PREDEFINED" and saved["payload"]["seed"] is None
        assert saved["payload"]["annotation_indices"] == data["annotation_indices"]
        assert saved["payload"]["removed_indices"] == data["removed_indices"]


@pytest.mark.parametrize("field,value", [("csv_sha256", "0"*64), ("row_count", 149),
    ("annotation_indices", []), ("reference_columns", []), ("removed_indices", list(range(29)))])
def test_invalid_bundle_cannot_execute(field, value):
    with pytest.raises(ValueError):
        prepare_experiment(IRIS_CONFIG, 0, 0.2, "pca", predefined_bundle={**bundle(), field: value})


def controller(data):
    ctrl = SimpleNamespace(_preparing_experiment=False, setup_elements={"source_toggle": SimpleNamespace(value="PREDEFINED")},
        experiment_source="PREDEFINED", predefined_selection=CatalogSet(8, 1, "iris", 0.2, True),
        active_screen="setup", _setup_screen_marker=object(), seed=42, na_fraction=0.1, dataset_name="iris", projection_name="pca",
        predefined_cache=PredefinedCache(LocalStorage(":memory:")),
        api_client=SimpleNamespace(base_url="http://test", get_execution_set=AsyncMock(return_value=ApiResult(success=True, data=data))),
        _set_exit_guard=Mock(), _update_status_badge=Mock(), show_setup=Mock(), show_experiment=Mock())
    return ctrl


def test_controller_starts_and_persists_the_actual_predefined_execution():
    ctrl = controller(bundle())
    with patch("dahlia.app.controller.start_algorithm_predictions", return_value="future"):
        asyncio.run(AppController.start_experiment(ctrl))
    ctrl.show_experiment.assert_called_once()
    assert ctrl.experiment.seed == 0 and ctrl.experiment.predefined_set_id == 8
    ctrl.experiment.answers = {int(i): float(ctrl.experiment.original.loc[i, IRIS_CONFIG.incomplete_column]) for i in ctrl.experiment.annotation_indices}
    ctrl.algorithm_predictions = calculate_algorithm_predictions(ctrl.experiment)
    ctrl.results = calculate_results(ctrl.experiment, ctrl.algorithm_predictions)
    ctrl.storage = LocalStorage(":memory:")
    ctrl.current_user = None
    AppController._save_current_experiment(ctrl)
    AppController._save_current_experiment(ctrl)
    assert len(ctrl.local_experiments) == 1
    assert ctrl.local_experiments[0]["payload"]["seed"] is None


def test_double_click_and_late_navigation_do_not_start_experiment():
    async def run():
        ctrl = controller(bundle())
        pending = asyncio.Future()
        async def read(_):
            return await pending
        ctrl.api_client.get_execution_set.side_effect = read
        task = asyncio.create_task(AppController.start_experiment(ctrl))
        await asyncio.sleep(0)
        await AppController.start_experiment(ctrl)
        assert ctrl.api_client.get_execution_set.await_count == 1
        ctrl.active_screen = "profile"
        pending.set_result(ApiResult(success=True, data=bundle()))
        await task
        ctrl.show_experiment.assert_not_called()
        assert not ctrl._preparing_experiment
    asyncio.run(run())


@pytest.mark.parametrize("response", [ApiResult(success=False, is_offline=True),
    ApiResult(success=False, status_code=409, error="Set is inactive"),
    ApiResult(success=True, data={**bundle(), "predefined_set_id": 99})])
def test_failed_or_changed_definition_does_not_start(response):
    ctrl = controller(bundle())
    ctrl.api_client.get_execution_set.return_value = response
    with patch("dahlia.app.controller.start_algorithm_predictions") as predictions:
        asyncio.run(AppController.start_experiment(ctrl))
    ctrl.show_setup.assert_called_once()
    ctrl.show_experiment.assert_not_called()
    predictions.assert_not_called()
    assert not ctrl._preparing_experiment


def test_seeded_controller_still_uses_the_seed_without_api():
    ctrl = controller(bundle())
    ctrl.experiment_source = "SEEDED"
    ctrl.setup_elements["source_toggle"].value = "SEEDED"
    ctrl.set_seed_text = lambda value: AppController.set_seed_text(ctrl, value)
    with patch("dahlia.app.controller.start_algorithm_predictions", return_value="future"):
        asyncio.run(AppController.start_experiment(ctrl))
    ctrl.api_client.get_execution_set.assert_not_awaited()
    ctrl.show_experiment.assert_called_once()
    assert ctrl.experiment.seed == 42 and ctrl.experiment.source_type == "SEEDED"
    assert ctrl.experiment.predefined_set_id is None
