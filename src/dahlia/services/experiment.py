"""Experiment preparation, background imputations, and metric calculation."""

from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Mapping

import math
import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, root_mean_squared_error

from dahlia.datasets import ExperimentSampler
from dahlia.imputation import (
    ClusterKNNImputer,
    ClusterMeanImputer,
    KNNImputer,
    MICEImputer,
    MeanImputer,
    RandomForestImputer,
)

from .config import DatasetConfig, METHOD_ORDER, TOTAL_STEPS
from .data import load_dataset
from .projection import compute_projection


@dataclass(slots=True)
class PreparedExperiment:
    config: DatasetConfig
    seed: int
    na_fraction: float
    projection_name: str
    original: pd.DataFrame
    incomplete: pd.DataFrame
    coordinates: pd.DataFrame
    removed_indices: np.ndarray
    annotation_indices: np.ndarray
    value_min: float
    value_max: float
    display_ticks: tuple[float, ...]
    answers: dict[int, float] = field(default_factory=dict)

    @property
    def current_step(self) -> int:
        return len(self.answers) + 1

    @property
    def is_complete(self) -> bool:
        return len(self.answers) == len(self.annotation_indices)

    @property
    def current_index(self) -> int:
        if self.is_complete:
            raise IndexError("The experiment has no remaining points.")
        return int(self.annotation_indices[len(self.answers)])


def precision_digits(precision: float) -> int:
    return max(0, -Decimal(str(precision)).as_tuple().exponent)


def snap_value(
    value: float,
    minimum: float,
    maximum: float,
    precision: float,
) -> float:
    """Clamp and snap a value to the configured dataset precision."""
    clamped = min(max(float(value), minimum), maximum)
    steps = round((clamped - minimum) / precision)
    snapped = minimum + steps * precision
    return round(
        min(max(snapped, minimum), maximum),
        precision_digits(precision),
    )


def build_display_ticks(
    minimum: float,
    maximum: float,
    precision: float,
    max_labels: int = 9,
) -> tuple[float, ...]:
    """Return evenly spaced tick labels aligned to nice multiples of precision.

    Iterates over multipliers (1, 2, 5, 10, …) of *precision* and picks the
    smallest one whose tick count does not exceed *max_labels*.  This ensures
    the slider and the colorbar always show clean, evenly spaced labels.
    """
    digits = precision_digits(precision)
    span = round(maximum - minimum, digits + 4)
    if span <= 0:
        return (round(minimum, digits),)

    for multiplier in (1, 2, 5, 10, 20, 50, 100, 200, 500, 1000):
        step = round(multiplier * precision, digits + 4)
        # First tick: smallest multiple of step that is >= minimum.
        first = math.ceil(round(minimum / step, 10)) * step
        first = round(first, digits)
        ticks: list[float] = []
        t = first
        while round(t, digits) <= round(maximum, digits) + 1e-9:
            ticks.append(round(t, digits))
            t = round(t + step, digits)
        if ticks and len(ticks) <= max_labels:
            return tuple(ticks)

    # Fallback: just the two endpoints.
    return (round(minimum, digits), round(maximum, digits))


def prepare_experiment(
    config: DatasetConfig,
    seed: int,
    na_fraction: float,
    projection_name: str,
) -> PreparedExperiment:
    """Build all deterministic data needed by the active experiment screen."""
    original = load_dataset(config)
    removed, annotations = ExperimentSampler(seed).select_experiment_points(
        original,
        na_fraction=na_fraction,
        n_imputation_steps=TOTAL_STEPS,
    )

    incomplete = original.copy(deep=True)
    incomplete.loc[removed, config.incomplete_column] = np.nan

    observed = incomplete[config.incomplete_column].dropna()
    digits = precision_digits(config.precision)
    minimum = round(
        float(observed.min() - 3 * config.precision),
        digits,
    )
    maximum = round(
        float(observed.max() + 3 * config.precision),
        digits,
    )

    coordinates = compute_projection(
        original,
        config,
        projection_name,
        seed,
    )
    return PreparedExperiment(
        config=config,
        seed=seed,
        na_fraction=na_fraction,
        projection_name=projection_name,
        original=original,
        incomplete=incomplete,
        coordinates=coordinates,
        removed_indices=removed,
        annotation_indices=annotations,
        value_min=minimum,
        value_max=maximum,
        display_ticks=build_display_ticks(
            minimum,
            maximum,
            config.precision,
        ),
    )


def _method_factories(experiment: PreparedExperiment):
    cfg = experiment.config
    seed = experiment.seed
    return {
        "Mean": MeanImputer(),
        "Cluster Mean": ClusterMeanImputer(
            n_clusters=cfg.number_of_clusters,
            random_state=seed,
        ),
        "KNN": KNNImputer(n_neighbors=cfg.knn_number_of_neighbors),
        "Cluster KNN": ClusterKNNImputer(
            n_clusters=cfg.number_of_clusters,
            n_neighbors=cfg.knn_number_of_neighbors,
            random_state=seed,
        ),
        "Random Forest": RandomForestImputer(random_state=seed),
        "MICE": MICEImputer(random_state=seed),
    }


def calculate_algorithm_predictions(
    experiment: PreparedExperiment,
) -> dict[str, pd.Series]:
    """Impute all missing points with all six baseline methods."""
    frame = experiment.incomplete.loc[
        :,
        experiment.config.numeric_model_columns,
    ]
    target = experiment.config.incomplete_column
    methods = _method_factories(experiment)
    predictions: dict[str, pd.Series] = {}

    with ThreadPoolExecutor(
        max_workers=len(methods),
        thread_name_prefix="dahlia-imputer",
    ) as pool:
        pending = {
            pool.submit(imputer.fit_transform, frame): name
            for name, imputer in methods.items()
        }
        for future in as_completed(pending):
            name = pending[future]
            transformed = future.result()
            if transformed[target].isna().any():
                raise RuntimeError(f"{name} returned missing values.")
            predictions[name] = transformed.loc[
                experiment.removed_indices,
                target,
            ].copy()

    return predictions


_BACKGROUND_EXECUTOR = ThreadPoolExecutor(
    max_workers=1,
    thread_name_prefix="dahlia-baselines",
)


def start_algorithm_predictions(
    experiment: PreparedExperiment,
) -> Future[dict[str, pd.Series]]:
    """Start baseline calculations while the annotator works."""
    return _BACKGROUND_EXECUTOR.submit(
        calculate_algorithm_predictions,
        experiment,
    )


def calculate_results(
    experiment: PreparedExperiment,
    algorithm_predictions: Mapping[str, pd.Series],
) -> pd.DataFrame:
    """Compare the annotator and methods on exactly the same 15 points."""
    annotation_indices = [int(index) for index in experiment.annotation_indices]
    if set(experiment.answers) != set(annotation_indices):
        raise ValueError(
            "All 15 annotation values must be confirmed before calculating results."
        )

    target = experiment.config.incomplete_column
    truth = experiment.original.loc[
        annotation_indices,
        target,
    ].to_numpy(dtype=float)
    rows: list[dict[str, float | str]] = []

    annotator = np.asarray(
        [experiment.answers[index] for index in annotation_indices],
        dtype=float,
    )
    rows.append(
        {
            "Method": "Annotator",
            "MAE": mean_absolute_error(truth, annotator),
            "RMSE": root_mean_squared_error(truth, annotator),
        }
    )

    for method in METHOD_ORDER[1:]:
        if method not in algorithm_predictions:
            raise KeyError(f"Missing predictions for method: {method}")
        predicted = algorithm_predictions[method].reindex(
            annotation_indices
        ).to_numpy(dtype=float)
        rows.append(
            {
                "Method": method,
                "MAE": mean_absolute_error(truth, predicted),
                "RMSE": root_mean_squared_error(truth, predicted),
            }
        )

    return pd.DataFrame(rows, columns=["Method", "MAE", "RMSE"])
