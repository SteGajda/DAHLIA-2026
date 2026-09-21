"""CSV loading, application resource lookup, and validation."""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

from .config import DatasetConfig


class DatasetValidationError(ValueError):
    """Raised when a configured dataset cannot be used by the experiment."""


def project_root() -> Path:
    """Return the source checkout root or the PyInstaller extraction root."""
    frozen_root = getattr(sys, "_MEIPASS", None)
    if frozen_root:
        return Path(frozen_root)
    return Path(__file__).resolve().parents[3]


def resolve_project_path(path: Path) -> Path:
    if path.is_absolute():
        return path

    candidates = (
        Path.cwd() / path,
        project_root() / path,
        Path(sys.executable).resolve().parent / path,
    )
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[1]


def load_dataset(config: DatasetConfig) -> pd.DataFrame:
    """Load and validate a dataset without changing its row order."""
    path = resolve_project_path(config.path)
    if not path.exists():
        raise DatasetValidationError(f"Dataset file was not found: {path}")

    df = pd.read_csv(path)
    required = {
        "Id",
        config.incomplete_column,
        config.target_column,
        *config.reference_columns,
    }
    missing = required.difference(df.columns)
    if missing:
        raise DatasetValidationError(
            f"Dataset is missing required columns: {sorted(missing)}"
        )
    if df.empty:
        raise DatasetValidationError("Dataset is empty.")
    if df["Id"].duplicated().any():
        raise DatasetValidationError("Id values must be unique.")

    numeric_columns = list(config.numeric_model_columns)
    if df[numeric_columns].isna().any().any():
        raise DatasetValidationError(
            "Required numeric columns already contain missing values."
        )
    non_numeric = df[numeric_columns].select_dtypes(exclude="number").columns
    if len(non_numeric):
        raise DatasetValidationError(
            f"Columns must be numeric: {non_numeric.tolist()}"
        )

    # The DataFrame index is the experiment point identifier. The CSV is assumed
    # to be correctly ordered, so only a clean zero-based index is established.
    return df.reset_index(drop=True)
