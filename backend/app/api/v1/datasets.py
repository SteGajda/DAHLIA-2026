"""Read-only central dataset catalog for predefined set managers."""

from fastapi import APIRouter, Depends
from sqlalchemy import select, true
from sqlalchemy.orm import Session

from app.api.deps import require_predefined_set_manager
from app.db.session import get_db
from app.models.experiment import Dataset
from app.models.user import AppUser
from app.schemas.dataset import DatasetSummary

router = APIRouter()


@router.get("", response_model=list[DatasetSummary])
def list_datasets(
    db: Session = Depends(get_db),
    _user: AppUser = Depends(require_predefined_set_manager),
) -> list[DatasetSummary]:
    """List every active central dataset, without reading CSV blobs.

    Order is stable by dataset_id. Small datasets remain visible; whether a
    fraction produces at least 15 missing points is validated separately.
    """
    rows = db.execute(
        select(Dataset.dataset_id, Dataset.name, Dataset.row_count)
        .where(Dataset.is_active == true())
        .order_by(Dataset.dataset_id)
    ).all()
    return [DatasetSummary(dataset_id=row.dataset_id, name=row.name,
                           row_count=row.row_count) for row in rows]
