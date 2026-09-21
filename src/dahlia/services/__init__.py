"""Application-independent services for the DAHLIA desktop client."""

from .config import (
    APP_VERSION,
    DATASETS,
    IRIS_CONFIG,
    MAX_SEED,
    METHOD_ORDER,
    NA_FRACTIONS,
    PROJECTIONS,
    TOTAL_STEPS,
    DatasetConfig,
)
from .data import DatasetValidationError, load_dataset
from .experiment import (
    PreparedExperiment,
    calculate_algorithm_predictions,
    calculate_results,
    prepare_experiment,
    snap_value,
    start_algorithm_predictions,
)
from .projection import ProjectionError, compute_projection

__all__ = [
    "APP_VERSION",
    "DATASETS",
    "IRIS_CONFIG",
    "MAX_SEED",
    "METHOD_ORDER",
    "NA_FRACTIONS",
    "PROJECTIONS",
    "TOTAL_STEPS",
    "DatasetConfig",
    "DatasetValidationError",
    "PreparedExperiment",
    "ProjectionError",
    "calculate_algorithm_predictions",
    "calculate_results",
    "compute_projection",
    "load_dataset",
    "prepare_experiment",
    "snap_value",
    "start_algorithm_predictions",
]
