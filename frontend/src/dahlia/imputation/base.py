"""
Base classes and interfaces for DAHLIA imputation methods.
"""
from abc import ABC, abstractmethod

import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.utils.validation import check_is_fitted


class BaseDAHLIAImputer(ABC, BaseEstimator, TransformerMixin):
    """
    Abstract base class for all imputation methods in the DAHLIA project.

    This class provides the standard scikit-learn interface by inheriting
    from BaseEstimator and TransformerMixin. It handles common input
    validations, ensuring that input data is a pandas DataFrame with
    numeric columns only, and that column consistency is maintained
    between fit and transform operations.

    Subclasses must implement the `_fit` and `_transform` methods.

    Attributes
    ----------
    feature_names_in_ : numpy.ndarray of shape (n_features,)
        Names of features seen during `fit`.
        Used to ensure column consistency between `fit` and `transform`.
    """

    def fit(self, X: pd.DataFrame, y=None) -> "BaseDAHLIAImputer":
        """
        Fit the imputer to the dataset.

        Parameters
        ----------
        X : pandas DataFrame of shape (n_samples, n_features)
            Input dataset to fit the imputer.
            Must contain only numeric columns.

        y : None, default=None
            Ignored. Included for compatibility with scikit-learn.

        Returns
        -------
        self : BaseDAHLIAImputer
            Fitted imputer ready for transformation.
        """
        X = self._validate_dataframe(X)

        self.feature_names_in_ = np.array(X.columns, dtype=object)

        self._fit(X)

        return self

    def transform(self, X: pd.DataFrame) -> pd.DataFrame:
        """
        Impute missing values in the dataset.

        Parameters
        ----------
        X : pandas DataFrame of shape (n_samples, n_features)
            Dataset to impute. Must contain only numeric columns and have
            the same columns as the dataset used during `fit`.

        Returns
        -------
        X_imputed : pandas DataFrame of shape (n_samples, n_features)
            Fully imputed dataset containing no missing values.

        Raises
        ------
        sklearn.exceptions.NotFittedError
            If the imputer has not been fitted yet.
        ValueError
            If the columns of X do not match those seen during `fit`.
        """
        check_is_fitted(self, attributes=["feature_names_in_"])

        X = self._validate_dataframe(X)
        if list(X.columns) != list(self.feature_names_in_):
            raise ValueError(
                f"X.columns must match the columns seen during fit {list(self.feature_names_in_)}, "
                f"got {list(X.columns)} instead"
            )

        X_imputed = self._transform(X)

        return X_imputed

    def _validate_dataframe(self, X) -> pd.DataFrame:
        """
        Validate that the input is a numeric pandas DataFrame and return a copy.

        Parameters
        ----------
        X : object
            Object to validate.

        Returns
        -------
        X : pandas DataFrame
            A copy of the input DataFrame.

        Raises
        ------
        TypeError
            If X is not a pandas DataFrame.
        ValueError
            If X contains non-numeric columns.
        """
        if not isinstance(X, pd.DataFrame):
            raise TypeError(f"Input must be a pandas DataFrame, got {type(X).__name__} instead.")

        non_numeric = [col for col in X.columns if not pd.api.types.is_numeric_dtype(X[col])]
        if non_numeric:
            raise ValueError(
                f"All columns must be numeric. Non-numeric columns found: {non_numeric}"
            )

        return X.copy()

    @abstractmethod
    def _fit(self, X: pd.DataFrame) -> None:
        """
        Internal fit logic to be implemented by subclasses.

        This method is called by `fit` after input validation and column
        storage. Subclasses should store all learned parameters as
        attributes with a trailing underscore (e.g., ``imputer_``).

        Parameters
        ----------
        X : pandas DataFrame of shape (n_samples, n_features)
            Validated and copied input dataset.

        Raises
        ------
        NotImplementedError
            If a subclass does not override this method.
        """
        pass

    @abstractmethod
    def _transform(self, X: pd.DataFrame) -> pd.DataFrame:
        """
        Internal transform logic to be implemented by subclasses.

        This method is called by `transform` after input validation and
        column consistency checks. The input X is guaranteed to be a
        validated copy with columns matching those seen during fit.

        Parameters
        ----------
        X : pandas DataFrame of shape (n_samples, n_features)
            Validated and copied dataset to impute.

        Returns
        -------
        X_imputed : pandas DataFrame of shape (n_samples, n_features)
            Fully imputed dataset containing no missing values.

        Raises
        ------
        NotImplementedError
            If a subclass does not override this method.
        """
        pass


__all__ = [
    "BaseDAHLIAImputer",
]