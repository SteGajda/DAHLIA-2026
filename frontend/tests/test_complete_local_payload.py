"""Persistence of complete scientific results, independent of live UI/network."""

import json
import sqlite3
from unittest.mock import MagicMock

import numpy as np
import pandas as pd
import pytest

from dahlia.app.controller import AppController
from dahlia.services.config import IRIS_CONFIG, METHOD_ORDER
from dahlia.services.experiment import PreparedExperiment, build_storage_details
from dahlia.services.local_storage import LocalStorage


def sample_experiment():
    original = pd.DataFrame({"SepalLengthCm": [4.1, 5.2, 6.3, 7.4]}, index=[10, 20, 30, 40])
    experiment = PreparedExperiment(
        config=IRIS_CONFIG, seed=42, na_fraction=0.3, projection_name="pca",
        original=original, incomplete=original.copy(), coordinates=pd.DataFrame(),
        removed_indices=np.array([10, 30, 40]), annotation_indices=np.array([40, 10]),
        value_min=4.0, value_max=8.0, display_ticks=(4.0, 8.0),
        answers={40: 7.0, 10: 4.0},
    )
    # Intentionally different order: persistence must align by row identifier.
    predictions = {method: pd.Series([7.3, 4.2, 6.4], index=[40, 10, 30])
                   for method in METHOD_ORDER[1:]}
    return experiment, predictions


def controller_for(storage):
    controller = AppController(root=MagicMock(), storage=storage)
    controller.experiment, controller.algorithm_predictions = sample_experiment()
    controller.results = pd.DataFrame([{"Method": "Annotator", "MAE": 0.2, "RMSE": 0.3}])
    return controller


def test_complete_payload_survives_restart_and_preserves_all_points(tmp_path):
    path = tmp_path / "local.db"
    controller = controller_for(LocalStorage(path))
    controller._save_current_experiment()
    uid = controller.local_experiments[0]["experiment_uid"]
    controller._save_current_experiment()
    records = LocalStorage(path).get_experiments()
    assert len(records) == 1
    assert records[0]["experiment_uid"] == uid
    assert records[0]["sync_status"] == "Local only"
    assert records[0]["user_id"] is None
    payload = records[0]["payload"]
    assert payload["payload_schema_version"] == 2
    assert payload["app_version"]
    assert payload["removed_indices"] == [10, 30, 40]
    assert payload["annotation_indices"] == [40, 10]
    assert payload["answers"] == {"40": 7.0, "10": 4.0}
    assert payload["true_values"] == {"10": 4.1, "30": 6.3, "40": 7.4}
    assert set(payload["algorithm_predictions"]) == set(METHOD_ORDER[1:])
    for values in payload["algorithm_predictions"].values():
        assert values == {"10": 4.2, "30": 6.4, "40": 7.3}
    assert payload["dataset_config"]["incomplete_column"] == "SepalLengthCm"
    assert "original" not in payload and "incomplete" not in payload


def test_existing_unversioned_record_is_read_without_rewriting(tmp_path):
    path = tmp_path / "old.db"
    storage = LocalStorage(path)
    controller = controller_for(storage)
    uid = storage.save_experiment(
        dataset_name="iris", seed=0, na_fraction=0.1, projection="pca",
        results_df=controller.results, answers={10: 4.0}, annotation_indices=[10],
    )
    with sqlite3.connect(path) as conn:
        old_payload = json.loads(conn.execute("SELECT payload_json FROM local_experiments").fetchone()[0])
        old_payload.pop("payload_schema_version")
        old_json = json.dumps(old_payload)
        conn.execute("UPDATE local_experiments SET payload_json = ?", (old_json,))
    record = LocalStorage(path).get_experiments()[0]
    assert record["experiment_uid"] == uid
    assert record["answers"] == {10: 4.0}
    assert record["payload"]["payload_schema_version"] == 1
    with sqlite3.connect(path) as conn:
        assert conn.execute("SELECT payload_json FROM local_experiments").fetchone()[0] == old_json


def test_incomplete_experiment_is_not_saved():
    storage = LocalStorage(":memory:")
    controller = controller_for(storage)
    controller.experiment.answers.pop(10)
    with pytest.raises(ValueError, match="fully annotated"):
        controller._save_current_experiment()
    assert storage.get_experiments() == []
    assert controller._saved_experiment_uid is None


@pytest.mark.parametrize("problem", ["missing_method", "missing_point", "nan", "infinity", "duplicate_index"])
def test_invalid_predictions_are_rejected(problem):
    experiment, predictions = sample_experiment()
    if problem == "missing_method":
        predictions.pop("Mean")
    elif problem == "missing_point":
        predictions["Mean"] = predictions["Mean"].drop(30)
    elif problem == "duplicate_index":
        predictions["Mean"] = pd.Series([4.2, 6.4, 7.3], index=[10, 10, 40])
    else:
        predictions["Mean"].loc[30] = np.nan if problem == "nan" else np.inf
    with pytest.raises(ValueError):
        build_storage_details(experiment, predictions)


def test_failed_write_can_be_retried_without_duplicate(tmp_path, monkeypatch):
    storage = LocalStorage(tmp_path / "retry.db")
    controller = controller_for(storage)
    real_save = storage.save_experiment
    def fail(**kwargs):
        raise sqlite3.OperationalError("disk full")
    monkeypatch.setattr(storage, "save_experiment", fail)
    with pytest.raises(sqlite3.OperationalError):
        controller._save_current_experiment()
    assert controller._saved_experiment_uid is None
    monkeypatch.setattr(storage, "save_experiment", real_save)
    controller._save_current_experiment()
    controller._save_current_experiment()
    assert len(storage.get_experiments()) == 1
