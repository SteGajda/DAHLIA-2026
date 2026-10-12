"""Version 2 completed-experiment payload used by the desktop SQLite buffer."""

from typing import Annotated, Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, FiniteFloat, model_validator

Index = Annotated[int, Field(strict=True, ge=0)]
METHODS = ('Mean', 'Cluster Mean', 'KNN', 'Cluster KNN', 'Random Forest', 'MICE')


class DatasetConfiguration(BaseModel):
    model_config = ConfigDict(extra='forbid')
    incomplete_column: str = Field(min_length=1, max_length=128)
    target_column: str | None = Field(default=None, max_length=128)
    reference_columns: list[str]
    categorical_columns: list[str]
    precision: FiniteFloat = Field(gt=0)
    number_of_clusters: int = Field(strict=True, gt=0)
    knn_number_of_neighbors: int = Field(strict=True, gt=0)


class Metric(BaseModel):
    model_config = ConfigDict(extra='forbid')
    Method: str
    MAE: FiniteFloat = Field(ge=0)
    RMSE: FiniteFloat = Field(ge=0)


class CompletedExperiment(BaseModel):
    model_config = ConfigDict(extra='forbid')
    payload_schema_version: Literal[2]
    experiment_uid: UUID
    created_at: AwareDatetime
    dataset_name: str = Field(min_length=1, max_length=128)
    seed: int | None = Field(default=None, strict=True, ge=0, le=4294967295)
    na_fraction: FiniteFloat = Field(gt=0, lt=1, multiple_of=0.000001)
    projection: Literal['pca', 'tsne', 'umap']
    user_id: int | None = Field(default=None, strict=True, gt=0)
    app_version: str = Field(min_length=1, max_length=32)
    dataset_config: DatasetConfiguration
    annotation_indices: list[Index] = Field(min_length=15, max_length=15)
    removed_indices: list[Index] = Field(min_length=15)
    answers: dict[int, FiniteFloat]
    true_values: dict[int, FiniteFloat]
    algorithm_predictions: dict[str, dict[int, FiniteFloat]]
    metrics: list[Metric] = Field(min_length=7, max_length=7)
    source_type: Literal['SEEDED', 'PREDEFINED'] = 'SEEDED'
    predefined_set_id: int | None = Field(default=None, strict=True, gt=0)

    @model_validator(mode='after')
    def validate_complete(self):
        if self.experiment_uid.version != 4:
            raise ValueError('experiment_uid must be UUID v4.')
        if self.source_type == 'SEEDED':
            if self.seed is None or self.predefined_set_id is not None:
                raise ValueError('SEEDED requires a seed and no predefined_set_id.')
        elif self.seed is not None or self.predefined_set_id is None:
            raise ValueError('PREDEFINED requires predefined_set_id and no seed.')
        annotated, removed = set(self.annotation_indices), set(self.removed_indices)
        if len(annotated) != 15 or len(removed) != len(self.removed_indices):
            raise ValueError('Point indices must be unique.')
        if not annotated.issubset(removed) or set(self.answers) != annotated:
            raise ValueError('Answers must match all 15 annotated points.')
        if set(self.true_values) != removed:
            raise ValueError('True values must cover exactly all removed points.')
        if set(self.algorithm_predictions) != set(METHODS):
            raise ValueError('All six baseline methods are required.')
        if any(set(values) != removed for values in self.algorithm_predictions.values()):
            raise ValueError('Every method must predict every removed point.')
        if {metric.Method for metric in self.metrics} != {'Annotator', *METHODS}:
            raise ValueError('Exactly one metric record per predictor is required.')
        return self
