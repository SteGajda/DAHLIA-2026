"""Verification of seed generation reproducibility across Experiment Setup and Predefined Sets."""

import pandas as pd
import pytest

from dahlia.datasets.na_generator import ExperimentSampler
from dahlia.services.config import DATASETS, NA_FRACTIONS, TOTAL_STEPS
from dahlia.services.data import load_dataset
from dahlia.services.predefined_sets import CatalogDataset, PredefinedDraft


@pytest.mark.parametrize("dataset_name", list(DATASETS.keys()))
@pytest.mark.parametrize("na_fraction", list(NA_FRACTIONS))
@pytest.mark.parametrize("seed", [0, 1, 42, 123456, 999999])
def test_seed_produces_identical_points_and_order(dataset_name: str, na_fraction: float, seed: int) -> None:
    """Verify that a given seed generates identical removed points and evaluation order
    in Experiment Setup (using load_dataset) and in PredefinedDraft (using central row_count).
    """
    config = DATASETS[dataset_name]
    df = load_dataset(config)
    row_count = len(df)

    # 1. Selection in Experiment Setup flow
    removed_exp, annotations_exp = ExperimentSampler(seed).select_experiment_points(
        df,
        na_fraction=na_fraction,
        n_imputation_steps=TOTAL_STEPS,
    )

    # 2. Selection in PredefinedDraft flow
    item = CatalogDataset(
        dataset_id=1,
        name=dataset_name,
        row_count=row_count,
    )
    draft = PredefinedDraft()
    draft.select_dataset(item)
    draft.select_fraction(na_fraction)
    draft.generate_from_seed(str(seed))

    removed_draft = [int(x.strip()) for x in draft.removed_text.split(",") if x.strip()]
    annotations_draft = [int(x.strip()) for x in draft.annotation_text.split(",") if x.strip()]

    assert list(removed_exp) == removed_draft, (
        f"Removed points mismatch for {dataset_name}, fraction={na_fraction}, seed={seed}"
    )
    assert list(annotations_exp) == annotations_draft, (
        f"Annotation order mismatch for {dataset_name}, fraction={na_fraction}, seed={seed}"
    )
