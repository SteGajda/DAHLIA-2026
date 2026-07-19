"""
Iterative imputation methods for DAHLIA experiments.

This module contains imputers that model each feature with missing values
as a function of the remaining features and apply this model iteratively.
Current classes: RandomForestImputer, MICEImputer.
"""
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.experimental import enable_iterative_imputer
from sklearn.impute import IterativeImputer
from sklearn.utils.validation import check_is_fitted
from sklearn.linear_model import BayesianRidge

from .base import BaseDAHLIAImputer


class RandomForestImputer(BaseDAHLIAImputer):
    """
    Random Forest-based iterative imputer (often referred to as missForest).

    Missing values are imputed using an iterative approach where a
    Random Forest Regressor is trained for each feature with missing
    values, using the other features as inputs. This process is repeated
    multiple times to capture complex, non-linear relationships.

    Parameters
    ----------
    n_estimators : int, default=100
        The number of trees in the forest used for each feature's model.
        Must be an integer >= 1.

    max_depth : {int, None}, default=None
        The maximum depth of the trees. If None, nodes are expanded until
        all leaves are pure or until all leaves contain less than
        min_samples_split samples. If an integer, must be >= 1.

    max_iter : int, default=10
        Maximum number of imputation rounds to perform before returning
        the imputations computed during the final round.
        Must be an integer >= 1.

    random_state : {int, None}, default=None
        Seed for reproducibility of the random forest building process
        and the initial imputation. If None, randomness is not fixed.

    Attributes
    ----------
    feature_names_in_ : numpy.ndarray of shape (n_features,)
        Names of features seen during `fit`.
        Used to ensure column consistency between `fit` and `transform`.

    imputer_ : sklearn.impute.IterativeImputer
        The underlying scikit-learn IterativeImputer instance configured
        with a RandomForestRegressor.

    Notes
    -----
    ``IterativeImputer`` is currently marked as **experimental** in
    scikit-learn. Its API may change in future releases without prior
    deprecation notice. The enabling import
    ``from sklearn.experimental import enable_iterative_imputer``
    is therefore required and must precede the import of
    ``IterativeImputer``.

    Examples
    --------
    >>> imputer = RandomForestImputer(n_estimators=50, max_iter=5, random_state=42)
    >>> imputer.fit(X)
    >>> X_filled = imputer.transform(X)
    """

    def __init__(
        self,
        n_estimators=100,
        max_depth=None,
        max_iter=10,
        random_state=None
    ):
        self.n_estimators = n_estimators
        self.max_depth = max_depth
        self.max_iter = max_iter
        self.random_state = random_state

    def _fit(self, X: pd.DataFrame) -> None:
        """
        Fit the iterative Random Forest imputer on the dataset.

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
            If n_estimators or max_iter are not integers, or if max_depth
            is neither an integer nor None.
        ValueError
            If n_estimators < 1, max_iter < 1, or max_depth < 1.
        """
        if not isinstance(self.n_estimators, int):
            raise TypeError(
                f"n_estimators must be int, got {type(self.n_estimators).__name__}"
            )
        if self.n_estimators < 1:
            raise ValueError(f"n_estimators must be >= 1, got {self.n_estimators}")

        if not isinstance(self.max_iter, int):
            raise TypeError(
                f"max_iter must be int, got {type(self.max_iter).__name__}"
            )
        if self.max_iter < 1:
            raise ValueError(f"max_iter must be >= 1, got {self.max_iter}")

        if self.max_depth is not None:
            if not isinstance(self.max_depth, int):
                raise TypeError(
                    f"max_depth must be int or None, got {type(self.max_depth).__name__}"
                )
            if self.max_depth < 1:
                raise ValueError(f"max_depth must be >= 1, got {self.max_depth}")

        estimator = RandomForestRegressor(
            n_estimators=self.n_estimators,
            max_depth=self.max_depth,
            random_state=self.random_state,
            n_jobs=-1,
        )

        self.imputer_ = IterativeImputer(
            estimator=estimator,
            max_iter=self.max_iter,
            random_state=self.random_state,
            initial_strategy='mean',
        )

        self.imputer_.fit(X)

    def _transform(self, X: pd.DataFrame) -> pd.DataFrame:
        """
        Impute missing values using the trained Random Forest models.

        Parameters
        ----------
        X : pandas DataFrame of shape (n_samples, n_features)
            Dataset to impute.

        Returns
        -------
        X_imputed : pandas DataFrame of shape (n_samples, n_features)
            Imputed dataset with missing values replaced by Random
            Forest predictions.

        Raises
        ------
        sklearn.exceptions.NotFittedError
            If the imputer has not been fitted yet.
        """
        check_is_fitted(self, attributes=["imputer_"])

        X_filled = self.imputer_.transform(X)
        return pd.DataFrame(X_filled, columns=self.feature_names_in_, index=X.index)


class MICEImputer(BaseDAHLIAImputer):
    """
    Multiple Imputation by Chained Equations (MICE) imputer.

    Missing values are estimated iteratively. Each feature containing
    missing values is modeled using the remaining features.
    Bayesian Ridge regression is used as the estimator.

    Parameters
    ----------
    max_iter : int, default=10
        Maximum number of imputation iterations.

    tol : float, default=1e-3
        Convergence tolerance.

    sample_posterior : bool, default=False
        Whether to sample from the posterior predictive distribution.

    random_state : int or None, default=None
        Seed controlling randomness.
    """

    def __init__(
        self,
        max_iter=10,
        tol=1e-3,
        sample_posterior=False,
        random_state=None,
    ):
        self.max_iter = max_iter
        self.tol = tol
        self.sample_posterior = sample_posterior
        self.random_state = random_state

    def _fit(self, X: pd.DataFrame) -> None:
        if isinstance(self.max_iter, bool) or not isinstance(
            self.max_iter, int
        ):
            raise TypeError(
                f"max_iter must be int, got {type(self.max_iter).__name__}"
            )

        if self.max_iter < 1:
            raise ValueError(
                f"max_iter must be >= 1, got {self.max_iter}"
            )

        if isinstance(self.tol, bool) or not isinstance(
            self.tol, (int, float)
        ):
            raise TypeError(
                f"tol must be numeric, got {type(self.tol).__name__}"
            )

        if self.tol <= 0:
            raise ValueError(
                f"tol must be > 0, got {self.tol}"
            )

        if not isinstance(self.sample_posterior, bool):
            raise TypeError(
                "sample_posterior must be bool, "
                f"got {type(self.sample_posterior).__name__}"
            )

        self.imputer_ = IterativeImputer(
            estimator=BayesianRidge(),
            max_iter=self.max_iter,
            tol=self.tol,
            sample_posterior=self.sample_posterior,
            random_state=self.random_state,
            initial_strategy="mean",
        )

        self.imputer_.fit(X)

    def _transform(self, X: pd.DataFrame) -> pd.DataFrame:
        check_is_fitted(self, attributes=["imputer_"])

        X_filled = self.imputer_.transform(X)

        return pd.DataFrame(
            X_filled,
            columns=self.feature_names_in_,
            index=X.index,
        )


__all__ = [
    "RandomForestImputer",
    "MICEImputer",
]