"""Leak-free deterministic two-dimensional projections."""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.decomposition import PCA
from sklearn.manifold import TSNE

from .config import DatasetConfig


class ProjectionError(RuntimeError):
    """Raised when a projection cannot be computed."""


def normalized_reference_matrix(
    df: pd.DataFrame,
    config: DatasetConfig,
) -> np.ndarray:
    """Repeat the previous survey app's max-based normalization.

    Only reference columns are used. The incomplete column, Id, and target
    column never influence point coordinates.
    """
    reference = df.loc[:, config.reference_columns].astype(float)
    maxima = reference.max(axis=0)
    if (maxima == 0).any():
        columns = maxima.index[maxima == 0].tolist()
        raise ProjectionError(
            f"Cannot normalize columns with a maximum of zero: {columns}"
        )
    return reference.div(maxima, axis=1).to_numpy()


def compute_projection(
    df: pd.DataFrame,
    config: DatasetConfig,
    projection: str,
    seed: int,
) -> pd.DataFrame:
    """Compute stable x/y coordinates once for the whole experiment.

    Notes
    -----
    UMAP is run with ``n_jobs=1`` (single-threaded).  When ``random_state``
    is set, UMAP internally forces single-thread execution anyway and emits a
    ``UserWarning`` if ``n_jobs != 1``.  Setting it explicitly suppresses the
    warning and mirrors the reproducibility constraint applied to
    ``RandomForestRegressor`` in the imputation layer.
    """
    matrix = normalized_reference_matrix(df, config)
    key = projection.lower()

    if key == "pca":
        projected = PCA(n_components=2, random_state=seed).fit_transform(matrix)
    elif key == "tsne":
        projected = TSNE(n_components=2, random_state=seed).fit_transform(matrix)
    elif key == "umap":
        try:
            from umap.umap_ import UMAP
        except ImportError as exc:
            raise ProjectionError(
                "UMAP is unavailable. Install the 'umap-learn' dependency."
            ) from exc
        projected = UMAP(
            n_components=2,
            init="random",
            random_state=seed,
            n_jobs=1,
        ).fit_transform(matrix)
    else:
        raise ProjectionError(f"Unknown projection: {projection}")

    return pd.DataFrame(projected, index=df.index, columns=["x", "y"])
