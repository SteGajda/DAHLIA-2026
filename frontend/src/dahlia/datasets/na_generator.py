"""
Logic for reproducible selection of missing data points and imputation subsets.
"""
import numpy as np
import pandas as pd


class ExperimentSampler:
    """
    Deterministic two-step sampler for selecting NA indices and imputation subsets.

    Uses a local ``np.random.default_rng`` instance seeded from ``seed``.
    A fresh generator is created at the start of each call to
    :meth:`select_experiment_points`, so calling the method multiple times
    on the same instance always returns the same result.

    Parameters
    ----------
    seed : int
        Non-negative integer seed. Controls both NA point selection and the
        imputation subset selection.

    Raises
    ------
    TypeError
        If ``seed`` is not an integer. Booleans are explicitly rejected even
        though ``bool`` is a subclass of ``int`` in Python.
    ValueError
        If ``seed`` is negative.
    """

    def __init__(self, seed: int) -> None:
        if isinstance(seed, bool) or not isinstance(seed, int):
            raise TypeError(
                f"seed must be a non-negative int, got {type(seed).__name__}"
            )
        if seed < 0:
            raise ValueError(f"seed must be >= 0, got {seed}")

        self.seed = seed

    def select_experiment_points(
        self,
        df: pd.DataFrame,
        na_fraction: float = 0.1,
        n_imputation_steps: int = 15,
    ):
        """
        Select NA indices and the imputation subset in two deterministic steps.

        Step 1 draws ``n_na`` indices from the full dataset index without
        replacement and sorts them to guarantee a stable, order-independent input
        for step 2.  Step 2 draws ``n_imputation_steps`` indices from the sorted
        NA pool without replacement.  The order returned by step 2 defines the
        sequence in which points are presented to the user and is preserved as-is.

        Parameters
        ----------
        df : pandas.DataFrame
            The original, complete dataset.
        na_fraction : float, default=0.1
            Fraction of rows to mark as missing. Must satisfy
            ``0.0 < na_fraction < 1.0``.
        n_imputation_steps : int, default=15
            Number of points to select from the NA pool for sequential
            imputation. Must be a positive integer and cannot exceed the total
            number of NA points derived from ``na_fraction``.

        Returns
        -------
        na_indices : numpy.ndarray of int
            Sorted array of indices of all points chosen to be removed.
        imputation_indices : numpy.ndarray of int
            Subset of ``na_indices`` that defines the imputation sequence.
            Order is deterministic for a given seed and is preserved intentionally.

        Raises
        ------
        TypeError
            If ``n_imputation_steps`` is not an integer (booleans are rejected).
        ValueError
            If ``na_fraction`` is not in (0.0, 1.0), if ``n_imputation_steps``
            is less than 1, or if ``n_imputation_steps`` exceeds the number of
            NA points derived from ``na_fraction``.
        """
        if isinstance(n_imputation_steps, bool) or not isinstance(
            n_imputation_steps, int
        ):
            raise TypeError(
                f"n_imputation_steps must be int, got "
                f"{type(n_imputation_steps).__name__}"
            )
        if n_imputation_steps < 1:
            raise ValueError(
                f"n_imputation_steps must be >= 1, got {n_imputation_steps}"
            )
        if not (0.0 < na_fraction < 1.0):
            raise ValueError(
                f"na_fraction must be in (0.0, 1.0), got {na_fraction}"
            )

        n_na = int(len(df) * na_fraction)

        if n_imputation_steps > n_na:
            raise ValueError(
                f"Cannot select {n_imputation_steps} imputation steps "
                f"from {n_na} NA points."
            )

        rng = np.random.default_rng(self.seed)

        all_indices = df.index.to_numpy()
        na_indices = rng.choice(all_indices, size=n_na, replace=False)
        na_indices.sort()

        imputation_indices = rng.choice(
            na_indices, size=n_imputation_steps, replace=False
        )

        return na_indices, imputation_indices


class PredefinedSetProvider:
    """
    Provides experiment indices from a predefined imputation set.

    A predefined set stores a fixed list of removed indices and a fixed
    imputation sequence created by a Superuser. The imputation
    order is preserved exactly as stored, so all users running the same
    predefined set see the same points in the same sequence.

    Parameters
    ----------
    predefined_set_data : dict
        Dictionary with the following required keys:

        ``'removed_indices'`` : list of int
            Indices of all points removed from the dataset.
        ``'imputed_indices'`` : list of int
            Ordered subset of ``removed_indices`` defining the imputation
            sequence. Order is preserved exactly as stored.

    Raises
    ------
    KeyError
        If ``predefined_set_data`` is missing one or both required keys.
    ValueError
        If either index list contains duplicates, or if any element of
        ``imputed_indices`` is not present in ``removed_indices``.
    """

    def __init__(self, predefined_set_data: dict) -> None:
        required_keys = {"removed_indices", "imputed_indices"}
        missing = required_keys - predefined_set_data.keys()
        if missing:
            raise KeyError(
                f"predefined_set_data is missing required keys: {missing}"
            )

        removed = list(predefined_set_data["removed_indices"])
        imputed = list(predefined_set_data["imputed_indices"])

        if len(removed) != len(set(removed)):
            raise ValueError("removed_indices contains duplicate entries.")
        if len(imputed) != len(set(imputed)):
            raise ValueError("imputed_indices contains duplicate entries.")

        removed_set = set(removed)
        invalid = [idx for idx in imputed if idx not in removed_set]
        if invalid:
            raise ValueError(
                f"imputed_indices contains entries not present in "
                f"removed_indices: {invalid}"
            )

        self.na_indices = np.array(removed)
        self.imputation_indices = np.array(imputed)

    def get_experiment_points(self):
        """
        Return the predefined removed and imputation indices.

        Returns
        -------
        na_indices : numpy.ndarray of int
            Indices of all removed points.
        imputation_indices : numpy.ndarray of int
            Ordered imputation sequence, preserved exactly as stored.
        """
        return self.na_indices, self.imputation_indices


__all__ = [
    "ExperimentSampler",
    "PredefinedSetProvider",
]