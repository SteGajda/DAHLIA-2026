import pandas as pd
import pytest

from dahlia.datasets import ExperimentSampler
from dahlia.services.config import MAX_SEED


def test_sampler_repeats_exactly_for_same_seed():
    df = pd.DataFrame({"value": range(150)})
    sampler = ExperimentSampler(42)
    first = sampler.select_experiment_points(df, 0.2, 15)
    second = sampler.select_experiment_points(df, 0.2, 15)
    assert first[0].tolist() == second[0].tolist()
    assert first[1].tolist() == second[1].tolist()


def test_sampler_accepts_maximum_supported_seed():
    df = pd.DataFrame({"value": range(150)})
    removed, selected = ExperimentSampler(MAX_SEED).select_experiment_points(
        df, 0.1, 15
    )
    assert len(removed) == 15
    assert len(selected) == 15


def test_sampler_rejects_invalid_number_of_steps():
    df = pd.DataFrame({"value": range(20)})
    with pytest.raises(ValueError):
        ExperimentSampler(0).select_experiment_points(df, 0.1, 15)
