"""Dataset metadata required by the predefined set authoring form."""

from pydantic import BaseModel, Field


class DatasetSummary(BaseModel):
    dataset_id: int = Field(gt=0)
    name: str
    row_count: int = Field(gt=0)
