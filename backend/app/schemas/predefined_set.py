"""API contract for complete predefined set definitions."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt


class PredefinedSetCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dataset_id: StrictInt = Field(gt=0)
    na_fraction: Literal[0.1, 0.2, 0.3]
    removed_indices: list[StrictInt]
    annotation_indices: list[StrictInt] = Field(min_length=15, max_length=15)


class PredefinedSetDefinition(BaseModel):
    predefined_set_id: int
    dataset_id: int
    na_fraction: float
    removed_indices: list[int]
    annotation_indices: list[int]
    created_by: int
    created_at: datetime
    is_active: bool
