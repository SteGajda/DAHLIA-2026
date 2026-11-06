"""Real industrial datasets retain positions and work with existing methods."""

import base64
import hashlib

import numpy as np
import pytest

from dahlia.services.config import DATASETS, METHOD_ORDER, WOLA_CONFIG, STAMP_TYPE_CONFIG
from dahlia.services.data import load_dataset, resolve_project_path
from dahlia.services.experiment import prepare_experiment, calculate_algorithm_predictions, calculate_results, build_storage_details
from dahlia.services.local_storage import LocalStorage


@pytest.mark.parametrize("name,count,clusters,neighbors,precision", [("wola", 926, 3, 5, 0.001), ("stamp_type", 462, 11, 3, 0.01)])
def test_configuration_and_positional_indices(name, count, clusters, neighbors, precision):
    cfg = DATASETS[name]
    frame = load_dataset(cfg)
    assert len(frame) == count and frame.index.tolist() == list(range(count))
    assert cfg.number_of_clusters == clusters and cfg.knn_number_of_neighbors == neighbors and cfg.precision == precision
    assert "Id" not in frame.columns
    assert "Unnamed: 0" not in cfg.numeric_model_columns
    assert cfg.target_column not in cfg.numeric_model_columns
    if name == "stamp_type":
        assert frame["No. observ"].duplicated().any()
        assert frame["Unnamed: 0"].tolist() != frame.index.tolist()
    assert len(cfg.reference_columns) == 6


@pytest.mark.parametrize("config", [WOLA_CONFIG, STAMP_TYPE_CONFIG])
def test_real_seeded_and_predefined_execution_offline_storage(config):
    experiment = prepare_experiment(config, 42, 0.2, "pca")
    content = resolve_project_path(config.path).read_bytes()
    # A manual reverse order must be retained, independently of the seed.
    order = list(reversed(experiment.annotation_indices.tolist()))
    package = dict(predefined_set_id=123, dataset_id=7, dataset_name=config.name, na_fraction=0.2,
        row_count=len(experiment.original), removed_indices=experiment.removed_indices.tolist(), annotation_indices=order,
        csv_base64=base64.b64encode(content).decode(), csv_sha256=hashlib.sha256(content).hexdigest(),
        imputed_column=config.incomplete_column, target_column=config.target_column,
        reference_columns=list(config.reference_columns), categorical_columns=list(config.categorical_columns), precision=config.precision)
    predefined = prepare_experiment(config, 999, 0.2, "pca", predefined_bundle=package)
    assert predefined.annotation_indices.tolist() == order and predefined.seed == 0
    predictions = calculate_algorithm_predictions(predefined)
    assert set(predictions) == set(METHOD_ORDER[1:])
    for values in predictions.values():
        assert np.isfinite(values.to_numpy()).all() and values.index.tolist() == predefined.removed_indices.tolist()
    predefined.answers = {int(i): float(predefined.original.loc[i, config.incomplete_column]) for i in predefined.annotation_indices}
    results = calculate_results(predefined, predictions)
    details = build_storage_details(predefined, predictions)
    assert details["dataset_config"]["number_of_clusters"] == config.number_of_clusters
    storage = LocalStorage(":memory:")
    storage.save_experiment(dataset_name=config.name, seed=None, source_type="PREDEFINED", predefined_set_id=123,
        na_fraction=0.2, projection="pca", results_df=results, answers=predefined.answers,
        annotation_indices=order, completed_data=details)
    assert storage.get_experiments()[0]["payload"]["annotation_indices"] == order
