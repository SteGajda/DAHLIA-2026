import numpy as np
import pandas as pd

from dahlia.services.config import IRIS_CONFIG, METHOD_ORDER, TOTAL_STEPS
from dahlia.services.experiment import (
    calculate_algorithm_predictions,
    calculate_results,
    prepare_experiment,
    snap_value,
)


def test_experiment_selection_and_projection_are_deterministic():
    first = prepare_experiment(IRIS_CONFIG, 42, 0.1, "pca")
    second = prepare_experiment(IRIS_CONFIG, 42, 0.1, "pca")

    np.testing.assert_array_equal(first.removed_indices, second.removed_indices)
    np.testing.assert_array_equal(first.annotation_indices, second.annotation_indices)
    np.testing.assert_allclose(first.coordinates, second.coordinates)
    assert len(first.annotation_indices) == TOTAL_STEPS
    assert first.incomplete[IRIS_CONFIG.incomplete_column].isna().sum() == 15


def test_slider_range_comes_from_observed_values_only():
    experiment = prepare_experiment(IRIS_CONFIG, 0, 0.3, "pca")
    observed = experiment.incomplete[IRIS_CONFIG.incomplete_column].dropna()
    assert experiment.value_min == round(float(observed.min() - 0.3), 1)
    assert experiment.value_max == round(float(observed.max() + 0.3), 1)


def test_snap_value_clamps_and_rounds_to_precision():
    assert snap_value(5.84, 4.0, 8.2, 0.1) == 5.8
    assert snap_value(99.0, 4.0, 8.2, 0.1) == 8.2
    assert snap_value(-4.0, 4.0, 8.2, 0.1) == 4.0


def test_all_methods_return_predictions_for_all_removed_points():
    experiment = prepare_experiment(IRIS_CONFIG, 0, 0.1, "pca")
    predictions = calculate_algorithm_predictions(experiment)

    assert set(predictions) == set(METHOD_ORDER[1:])
    for values in predictions.values():
        assert values.index.tolist() == experiment.removed_indices.tolist()
        assert not values.isna().any()


def test_results_use_only_the_same_15_annotation_points():
    experiment = prepare_experiment(IRIS_CONFIG, 0, 0.1, "pca")
    indices = [int(index) for index in experiment.annotation_indices]
    truth = experiment.original.loc[
        indices,
        IRIS_CONFIG.incomplete_column,
    ]
    experiment.answers = truth.to_dict()

    predictions = {
        method: pd.Series(
            experiment.original.loc[
                experiment.removed_indices,
                IRIS_CONFIG.incomplete_column,
            ].to_numpy(),
            index=experiment.removed_indices,
        )
        for method in METHOD_ORDER[1:]
    }
    results = calculate_results(experiment, predictions)

    assert results["Method"].tolist() == list(METHOD_ORDER)
    assert (results[["MAE", "RMSE"]].to_numpy() == 0).all()
