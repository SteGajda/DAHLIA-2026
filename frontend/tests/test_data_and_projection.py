from dataclasses import replace

import numpy as np

from dahlia.services.config import IRIS_CONFIG
from dahlia.services.data import load_dataset
from dahlia.services.projection import compute_projection, normalized_reference_matrix


def test_iris_csv_has_expected_schema_and_order():
    df = load_dataset(IRIS_CONFIG)
    assert len(df) == 150
    assert df.index.tolist() == list(range(150))
    assert df["Id"].tolist() == list(range(1, 151))
    assert df["Species"].dtype == object


def test_projection_matrix_uses_only_reference_columns():
    df = load_dataset(IRIS_CONFIG)
    baseline = normalized_reference_matrix(df, IRIS_CONFIG)

    changed = df.copy()
    changed[IRIS_CONFIG.incomplete_column] = 9999.0
    changed[IRIS_CONFIG.target_column] = "hidden"
    changed["Id"] = np.arange(1000, 1150)

    modified = normalized_reference_matrix(changed, IRIS_CONFIG)
    np.testing.assert_allclose(modified, baseline)


def test_pca_projection_is_deterministic_for_same_seed():
    df = load_dataset(IRIS_CONFIG)
    first = compute_projection(df, IRIS_CONFIG, "pca", seed=42)
    second = compute_projection(df, IRIS_CONFIG, "pca", seed=42)
    np.testing.assert_allclose(first.to_numpy(), second.to_numpy())
    assert list(first.columns) == ["x", "y"]
