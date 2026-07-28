"""
Imputation methods for the DAHLIA project.

This module provides a collection of statistical imputation algorithms
that can be used as baselines in DAHLIA experiments. All imputers follow
the scikit-learn estimator interface (fit / transform) and accept
pandas DataFrames as input.

Available classes
-----------------
BaseDAHLIAImputer : base.BaseDAHLIAImputer
    Abstract base class for all DAHLIA imputers.

MeanImputer : baselines.MeanImputer
    Column-mean imputation using scikit-learn SimpleImputer.

ClusterMeanImputer : baselines.ClusterMeanImputer
    K-Means cluster-centroid imputation on complete rows.

RandomForestImputer : trees.RandomForestImputer
    Iterative Random Forest imputation (missForest-style).
"""
