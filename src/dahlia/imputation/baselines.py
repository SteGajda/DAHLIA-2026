"""
Baseline imputation methods for DAHLIA experiments.
"""
import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.impute import SimpleImputer
from sklearn.utils.validation import check_is_fitted

from .base import BaseDAHLIAImputer


class MeanImputer(BaseDAHLIAImputer):
    """
    Simple mean-based imputer.

    Missing values are imputed using the mean of the observed values
    for each respective feature across the entire dataset.

    Attributes
    ----------
    feature_names_in_ : numpy.ndarray of shape (n_features,)
        Names of features seen during `fit`.
        Used to ensure column consistency between `fit` and `transform`.

    imputer_ : sklearn.impute.SimpleImputer
        The underlying scikit-learn SimpleImputer instance fitted
        on the training data.

    Examples
    --------
    >>> imputer = MeanImputer()
    >>> imputer.fit(X)
    >>> X_filled = imputer.transform(X)
    """

    def _fit(self, X: pd.DataFrame) -> None:
        """
        Fit the mean imputer on the dataset.

        Parameters
        ----------
        X : pandas DataFrame of shape (n_samples, n_features)
            Validated input dataset.

        Returns
        -------
        None
        """
        self.imputer_ = SimpleImputer(strategy='mean')
        self.imputer_.fit(X)

    def _transform(self, X: pd.DataFrame) -> pd.DataFrame:
        """
        Impute missing values using the learned column means.

        Parameters
        ----------
        X : pandas DataFrame of shape (n_samples, n_features)
            Dataset to impute.

        Returns
        -------
        X_imputed : pandas DataFrame of shape (n_samples, n_features)
            Imputed dataset with missing values replaced by column means.

        Raises
        ------
        sklearn.exceptions.NotFittedError
            If the imputer has not been fitted yet.
        """
        check_is_fitted(self, attributes=["imputer_"])

        X_filled = self.imputer_.transform(X)
        return pd.DataFrame(X_filled, columns=self.feature_names_in_, index=X.index)


class ClusterMeanImputer(BaseDAHLIAImputer):
    """
    Cluster mean-based imputer.

    Missing values are imputed using the centroid of the closest cluster.
    Clusters are formed using K-Means on the complete rows of the dataset.
    The nearest cluster for an incomplete observation is determined by
    Euclidean distance calculated only on the available (non-missing) features.

    Parameters
    ----------
    n_clusters : int, default=5
        Number of clusters used by the K-Means algorithm.
        Must be an integer >= 1.

    random_state : {int, None}, default=None
        Seed for reproducibility of internal stochastic components in K-Means.
        If None, randomness is not fixed.

    Attributes
    ----------
    feature_names_in_ : numpy.ndarray of shape (n_features,)
        Names of features seen during `fit`.
        Used to ensure column consistency between `fit` and `transform`.

    kmeans_ : sklearn.cluster.KMeans
        Fitted K-Means instance used to discover clusters.

    cluster_centers_ : numpy.ndarray of shape (n_clusters, n_features)
        Centroids of clusters learned from complete observations.
        Each centroid represents the mean position of a cluster in feature space.

    Notes
    -----
    Distance to cluster centroids is computed using only the non-missing
    features of each incomplete observation. Consequently, rows with
    different missing patterns are compared using different feature subsets.

    Examples
    --------
    >>> imputer = ClusterMeanImputer(n_clusters=4, random_state=42)
    >>> imputer.fit(X)
    >>> X_filled = imputer.transform(X)
    """

    def __init__(self, n_clusters=5, random_state=None):
        self.n_clusters = n_clusters
        self.random_state = random_state

    def _fit(self, X: pd.DataFrame) -> None:
        """
        Fit the imputer by applying K-Means on complete rows only.

        Parameters
        ----------
        X : pandas DataFrame of shape (n_samples, n_features)
            Validated input dataset. Only complete rows (without any
            missing values) are used for K-Means clustering.

        Returns
        -------
        None

        Raises
        ------
        TypeError
            If n_clusters is not an integer.
        ValueError
            If n_clusters < 1, if the dataset contains no complete rows,
            or if n_clusters exceeds the number of complete rows.
        """
        if not isinstance(self.n_clusters, int):
            raise TypeError(
                f"n_clusters must be int, got {type(self.n_clusters).__name__} instead"
            )
        if self.n_clusters < 1:
            raise ValueError(
                f"n_clusters must be >= 1, got {self.n_clusters} instead"
            )

        complete_mask = ~X.isna().any(axis=1)
        complete_rows = X[complete_mask]

        if complete_rows.empty:
            raise ValueError(
                "Cannot fit ClusterMeanImputer: no complete rows found in the dataset. "
                "At least one row without missing values is required."
            )

        if self.n_clusters > len(complete_rows):
            raise ValueError(
                f"n_clusters must be <= the number of complete rows ({len(complete_rows)}), "
                f"got {self.n_clusters} instead"
            )

        self.kmeans_ = KMeans(
            n_clusters=self.n_clusters,
            random_state=self.random_state,
            n_init='auto'
        )
        self.kmeans_.fit(complete_rows)

        self.cluster_centers_ = self.kmeans_.cluster_centers_

    def _transform(self, X: pd.DataFrame) -> pd.DataFrame:
        """
        Impute missing values by assigning each incomplete observation
        to the nearest cluster centroid.

        Distance to each centroid is computed using only the non-missing
        features of the observation being imputed.

        Parameters
        ----------
        X : pandas DataFrame of shape (n_samples, n_features)
            Dataset to impute.

        Returns
        -------
        X_imputed : pandas DataFrame of shape (n_samples, n_features)
            Imputed dataset with missing values replaced by the corresponding
            feature values of the nearest cluster centroid.

        Raises
        ------
        sklearn.exceptions.NotFittedError
            If the imputer has not been fitted yet.
        """
        check_is_fitted(self, attributes=["kmeans_", "cluster_centers_", "feature_names_in_"])

        incomplete_mask = X.isna().any(axis=1)
        incomplete = X[incomplete_mask]

        if incomplete.empty:
            return X.copy()

        X_imputed = X.copy()

        for idx, row in incomplete.iterrows():
            row_vals = row.values

            available_mask = ~np.isnan(row_vals)

            distances = np.linalg.norm(
                self.cluster_centers_[:, available_mask] - row_vals[available_mask],
                axis=1
            )

            nearest_center = self.cluster_centers_[np.argmin(distances)]

            missing_cols = row[row.isna()].index
            for col in missing_cols:
                col_idx = X.columns.get_loc(col)
                X_imputed.at[idx, col] = nearest_center[col_idx]

        return X_imputed


__all__ = [
    "MeanImputer",
    "ClusterMeanImputer",
]