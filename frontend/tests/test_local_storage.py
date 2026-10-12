"""Unit tests for offline-first local SQLite storage and controller sync."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pandas as pd
import pytest

from dahlia.app.controller import AppController
from dahlia.core.api_client import ApiResult
from dahlia.services.experiment import PreparedExperiment
from dahlia.services.local_storage import LocalStorage
from dahlia.services.config import IRIS_CONFIG, METHOD_ORDER


def _sample_results_df() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"Method": "Human Annotator", "MAE": 0.25, "RMSE": 0.35},
            {"Method": "Mean Imputer", "MAE": 0.45, "RMSE": 0.55},
        ]
    )


def test_init_and_empty_db() -> None:
    storage = LocalStorage(":memory:")
    assert storage.get_experiments() == []
    assert storage.get_unsynced_experiments() == []


def test_save_and_retrieve_experiment() -> None:
    storage = LocalStorage(":memory:")
    df = _sample_results_df()
    answers = {10: 4.5, 20: 3.2}
    annotations = [10, 20]

    uid = storage.save_experiment(
        dataset_name="iris",
        seed=123,
        na_fraction=0.15,
        projection="tsne",
        results_df=df,
        answers=answers,
        annotation_indices=annotations,
        user_id=None,
    )

    # Validate UUID format
    parsed_uuid = uuid.UUID(uid)
    assert str(parsed_uuid) == uid

    experiments = storage.get_experiments()
    assert len(experiments) == 1

    exp = experiments[0]
    assert exp["experiment_uid"] == uid
    assert exp["dataset"] == "iris"
    assert exp["seed"] == 123
    assert exp["na_fraction"] == 0.15
    assert exp["projection"] == "tsne"
    assert exp["sync_status"] == "Local only"
    assert exp["user_id"] is None
    assert exp["answers"] == answers
    assert exp["annotation_indices"] == annotations

    # DataFrame deserialisation check
    retrieved_df = exp["results"]
    assert isinstance(retrieved_df, pd.DataFrame)
    assert len(retrieved_df) == 2
    assert list(retrieved_df["Method"]) == ["Human Annotator", "Mean Imputer"]


def test_sync_status_lifecycle_and_unsynced_filter() -> None:
    storage = LocalStorage(":memory:")
    df = _sample_results_df()

    uid1 = storage.save_experiment(
        dataset_name="iris",
        seed=1,
        na_fraction=0.1,
        projection="tsne",
        results_df=df,
        answers={1: 2.0},
        annotation_indices=[1],
    )
    uid2 = storage.save_experiment(
        dataset_name="wine",
        seed=2,
        na_fraction=0.2,
        projection="pca",
        results_df=df,
        answers={2: 3.0},
        annotation_indices=[2],
    )

    unsynced = storage.get_unsynced_experiments()
    assert len(unsynced) == 2

    # Mark first experiment as synced
    assert storage.update_sync_status(uid1, "Synced") is True

    unsynced_after = storage.get_unsynced_experiments()
    assert len(unsynced_after) == 1
    assert unsynced_after[0]["experiment_uid"] == uid2

    # Verify status in full query
    all_exp = {e["experiment_uid"]: e["sync_status"] for e in storage.get_experiments()}
    assert all_exp[uid1] == "Synced"
    assert all_exp[uid2] == "Local only"


def test_assign_user_to_unassigned() -> None:
    storage = LocalStorage(":memory:")
    df = _sample_results_df()

    storage.save_experiment(
        dataset_name="iris",
        seed=1,
        na_fraction=0.1,
        projection="tsne",
        results_df=df,
        answers={},
        annotation_indices=[],
        user_id=None,
    )
    storage.save_experiment(
        dataset_name="wine",
        seed=2,
        na_fraction=0.1,
        projection="tsne",
        results_df=df,
        answers={},
        annotation_indices=[],
        user_id=None,
    )
    storage.save_experiment(
        dataset_name="boston",
        seed=3,
        na_fraction=0.1,
        projection="tsne",
        results_df=df,
        answers={},
        annotation_indices=[],
        user_id=77,
    )

    updated_count = storage.assign_user_to_unassigned(42)
    assert updated_count == 2

    experiments = storage.get_experiments()
    user_ids = [e["user_id"] for e in experiments]
    # Newest first: boston (77), wine (42), iris (42)
    assert 77 in user_ids
    assert user_ids.count(42) == 2
    assert None not in user_ids


def test_delete_experiment() -> None:
    storage = LocalStorage(":memory:")
    df = _sample_results_df()

    uid = storage.save_experiment(
        dataset_name="iris",
        seed=1,
        na_fraction=0.1,
        projection="tsne",
        results_df=df,
        answers={},
        annotation_indices=[],
    )
    assert len(storage.get_experiments()) == 1

    assert storage.delete_experiment(uid) is True
    assert len(storage.get_experiments()) == 0
    assert storage.delete_experiment(uid) is False


def test_controller_local_storage_lifecycle() -> None:
    storage = LocalStorage(":memory:")
    controller = AppController(root=MagicMock(), storage=storage)
    controller.show_my_results = MagicMock()

    assert controller.local_experiments == []

    # Mock an active completed experiment
    mock_exp = MagicMock(spec=PreparedExperiment)
    mock_exp.config.name = "iris"
    mock_exp.config = IRIS_CONFIG
    mock_exp.seed = 42
    mock_exp.na_fraction = 0.1
    mock_exp.projection_name = "tsne"
    mock_exp.answers = {5: 3.14}
    mock_exp.annotation_indices = [5]
    mock_exp.removed_indices = [5, 6]
    mock_exp.original = pd.DataFrame({"SepalLengthCm": [3.2, 4.1]}, index=[5, 6])

    controller.experiment = mock_exp
    controller.results = _sample_results_df()
    controller.algorithm_predictions = {
        method: pd.Series([3.1, 4.0], index=[5, 6])
        for method in METHOD_ORDER[1:]
    }

    controller._save_current_experiment()
    assert len(controller.local_experiments) == 1
    assert controller.local_experiments[0]["dataset"] == "iris"
    assert controller.local_experiments[0]["sync_status"] == "Local only"
    controller._save_current_experiment()
    assert len(storage.get_experiments()) == 1
    assert controller.local_experiments[0]["payload"]["payload_schema_version"] == 2

    # Delete experiment
    controller.delete_local_experiment(0)
    assert len(controller.local_experiments) == 0
    assert len(storage.get_experiments()) == 0


def test_controller_sync_local_experiments() -> None:
    import asyncio

    async def _test() -> None:
        storage = LocalStorage(":memory:")
        controller = AppController(root=MagicMock(), storage=storage)
        controller.is_online = True
        controller.current_user = {"user_id": 99, "email": "test@pw.edu.pl", "role": "USER"}

        # Save an experiment
        storage.save_experiment(
            dataset_name="iris",
            seed=1,
            na_fraction=0.1,
            projection="tsne",
            results_df=_sample_results_df(),
            answers={1: 2.0},
            annotation_indices=[1],
            user_id=None,
        )
        controller.local_experiments = storage.get_experiments()
        assert len(controller.local_experiments) == 1
        assert controller.local_experiments[0]["sync_status"] == "Local only"

        # Mock API sync call
        controller.api_client.sync_experiment = AsyncMock(
            return_value=ApiResult(success=True, status_code=201, data={"status": "ok"})
        )

        synced, failed = await controller.sync_local_experiments()
        assert synced == 1
        assert failed == 0

        assert controller.local_experiments[0]["sync_status"] == "Synced"
        assert storage.get_unsynced_experiments() == []

    asyncio.run(_test())

