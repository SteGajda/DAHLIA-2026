"""
K-nearest neighbors imputation methods for DAHLIA experiments.
"""

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.impute import KNNImputer as SklearnKNNImputer
from sklearn.utils.validation import check_is_fitted

from .base import BaseDAHLIAImputer


class KNNImputer(BaseDAHLIAImputer):
    """
    K-nearest neighbors imputer using uniform weights.

    Missing values are imputed using the arithmetic mean of values from
    the nearest neighboring observations. Every neighbor has the same weight.

    Parameters
    ----------
    n_neighbors : int, default=5
        Number of neighboring observations used for imputation.
        Must be an integer greater than or equal to 1.

    Attributes
    ----------
    feature_names_in_ : numpy.ndarray of shape (n_features,)
        Names of features seen during ``fit``.

    imputer_ : sklearn.impute.KNNImputer
        Fitted scikit-learn KNN imputer.

    Examples
    --------
    >>> imputer = KNNImputer(n_neighbors=3)
    >>> imputer.fit(X)
    >>> X_filled = imputer.transform(X)
    """

    def __init__(self, n_neighbors=5):
        self.n_neighbors = n_neighbors

    def _fit(self, X: pd.DataFrame) -> None:
        """
        Fit the KNN imputer.

        Parameters
        ----------
        X : pandas DataFrame of shape (n_samples, n_features)
            Validated input dataset.

        Returns
        -------
        None

        Raises
        ------
        TypeError
            If ``n_neighbors`` is not an integer.

        ValueError
            If ``n_neighbors`` is smaller than 1.
        """
        if isinstance(self.n_neighbors, bool) or not isinstance(
            self.n_neighbors, int
        ):
            raise TypeError(
                "n_neighbors must be int, "
                f"got {type(self.n_neighbors).__name__}"
            )

        if self.n_neighbors < 1:
            raise ValueError(
                f"n_neighbors must be >= 1, got {self.n_neighbors}"
            )

        all_missing_columns = X.columns[X.isna().all()].tolist()

        if all_missing_columns:
            raise ValueError(
                "Cannot fit KNNImputer because the following columns "
                f"contain only missing values: {all_missing_columns}"
            )

        self.imputer_ = SklearnKNNImputer(
            n_neighbors=self.n_neighbors,
            weights="uniform",
            metric="nan_euclidean",
        )

        self.imputer_.fit(X)

    def _transform(self, X: pd.DataFrame) -> pd.DataFrame:
        """
        Impute missing values using uniformly weighted nearest neighbors.

        Parameters
        ----------
        X : pandas DataFrame of shape (n_samples, n_features)
            Dataset to impute.

        Returns
        -------
        X_imputed : pandas DataFrame of shape (n_samples, n_features)
            Imputed dataset with the original columns and index.

        Raises
        ------
        sklearn.exceptions.NotFittedError
            If the imputer has not been fitted.
        """
        check_is_fitted(self, attributes=["imputer_"])

        X_filled = self.imputer_.transform(X)

        return pd.DataFrame(
            X_filled,
            columns=self.feature_names_in_,
            index=X.index,
        )


class ClusterKNNImputer(BaseDAHLIAImputer):
    """
    Cluster-based K-nearest neighbors imputer using uniform weights.

    Complete observations are divided into clusters using K-Means.
    A separate KNN imputer is fitted for every cluster.

    During transformation, an incomplete observation is assigned to the
    nearest cluster based only on its available features. Its missing values
    are then imputed using uniformly weighted neighbors from that cluster.

    Parameters
    ----------
    n_clusters : int, default=5
        Number of clusters used by K-Means.
        Must be an integer greater than or equal to 1.

    n_neighbors : int, default=5
        Number of neighboring observations used for imputation.
        Must be an integer greater than or equal to 1.

    random_state : int or None, default=None
        Seed controlling the randomness of K-Means.

    Attributes
    ----------
    feature_names_in_ : numpy.ndarray of shape (n_features,)
        Names of features seen during ``fit``.

    kmeans_ : sklearn.cluster.KMeans
        Fitted K-Means model.

    cluster_imputers_ : dict
        Fitted KNN imputer for each cluster.

    global_means_ : pandas.Series
        Global feature means used for observations containing only
        missing values.

    Examples
    --------
    >>> imputer = ClusterKNNImputer(
    ...     n_clusters=3,
    ...     n_neighbors=5,
    ...     random_state=42,
    ... )
    >>> imputer.fit(X)
    >>> X_filled = imputer.transform(X)
    """

    def __init__(
        self,
        n_clusters=5,
        n_neighbors=5,
        random_state=None,
    ):
        self.n_clusters = n_clusters
        self.n_neighbors = n_neighbors
        self.random_state = random_state

    def _fit(self, X: pd.DataFrame) -> None:
        """
        Fit K-Means and cluster-specific KNN imputers.

        Parameters
        ----------
        X : pandas DataFrame of shape (n_samples, n_features)
            Validated input dataset.

        Returns
        -------
        None

        Raises
        ------
        TypeError
            If ``n_clusters`` or ``n_neighbors`` is not an integer.

        ValueError
            If a parameter is outside its valid range, no complete rows
            exist, or the number of clusters exceeds the number of
            complete rows.
        """
        if isinstance(self.n_clusters, bool) or not isinstance(
            self.n_clusters, int
        ):
            raise TypeError(
                "n_clusters must be int, "
                f"got {type(self.n_clusters).__name__}"
            )

        if self.n_clusters < 1:
            raise ValueError(
                f"n_clusters must be >= 1, got {self.n_clusters}"
            )

        if isinstance(self.n_neighbors, bool) or not isinstance(
            self.n_neighbors, int
        ):
            raise TypeError(
                "n_neighbors must be int, "
                f"got {type(self.n_neighbors).__name__}"
            )

        if self.n_neighbors < 1:
            raise ValueError(
                f"n_neighbors must be >= 1, got {self.n_neighbors}"
            )

        complete_rows = X.dropna()

        if complete_rows.empty:
            raise ValueError(
                "Cannot fit ClusterKNNImputer: no complete rows "
                "were found in the dataset."
            )

        if self.n_clusters > len(complete_rows):
            raise ValueError(
                "n_clusters must be less than or equal to the number "
                f"of complete rows ({len(complete_rows)}), "
                f"got {self.n_clusters}"
            )

        self.kmeans_ = KMeans(
            n_clusters=self.n_clusters,
            random_state=self.random_state,
            n_init="auto",
        )

        cluster_labels = self.kmeans_.fit_predict(complete_rows)

        self.cluster_imputers_ = {}

        for cluster_id in range(self.n_clusters):
            cluster_rows = complete_rows.iloc[
                cluster_labels == cluster_id
            ]

            cluster_imputer = SklearnKNNImputer(
                n_neighbors=self.n_neighbors,
                weights="uniform",
                metric="nan_euclidean",
            )

            cluster_imputer.fit(cluster_rows)
            self.cluster_imputers_[cluster_id] = cluster_imputer

        self.global_means_ = complete_rows.mean()

    def _transform(self, X: pd.DataFrame) -> pd.DataFrame:
        """
        Impute missing values using cluster-specific KNN models.

        Parameters
        ----------
        X : pandas DataFrame of shape (n_samples, n_features)
            Dataset to impute.

        Returns
        -------
        X_imputed : pandas DataFrame of shape (n_samples, n_features)
            Imputed dataset with the original columns and index.

        Raises
        ------
        sklearn.exceptions.NotFittedError
            If the imputer has not been fitted.
        """
        check_is_fitted(
            self,
            attributes=[
                "kmeans_",
                "cluster_imputers_",
                "global_means_",
            ],
        )

        X_imputed = X.copy()
        incomplete_mask = X.isna().any(axis=1).to_numpy()

        if not incomplete_mask.any():
            return X_imputed

        incomplete_positions = np.flatnonzero(incomplete_mask)
        cluster_centers = self.kmeans_.cluster_centers_

        for row_position in incomplete_positions:
            row = X.iloc[row_position]

            available_mask = row.notna().to_numpy()
            missing_mask = row.isna().to_numpy()

            if not available_mask.any():
                X_imputed.iloc[row_position] = self.global_means_.to_numpy()
                continue

            row_values = row.to_numpy(dtype=float)

            distances = np.linalg.norm(
                cluster_centers[:, available_mask]
                - row_values[available_mask],
                axis=1,
            )

            nearest_cluster = int(np.argmin(distances))

            row_frame = pd.DataFrame(
                [row_values],
                columns=X.columns,
            )

            filled_values = self.cluster_imputers_[
                nearest_cluster
            ].transform(row_frame)[0]

            missing_positions = np.flatnonzero(missing_mask)

            X_imputed.iloc[
                row_position,
                missing_positions,
            ] = filled_values[missing_mask]

        return X_imputed


__all__ = [
    "KNNImputer",
    "ClusterKNNImputer",
]