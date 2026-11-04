"""Read predefined set metadata and persisted point order for managers."""

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.experiment import Dataset, PredefinedSet, PredefinedSetPoint
from app.schemas.predefined_set import PredefinedSetDefinition, PredefinedSetSummary


def list_predefined_sets(db: Session) -> list[PredefinedSetSummary]:
    """Include all authors and both active/inactive states, ordered by set ID."""
    rows = db.execute(
        select(
            PredefinedSet.predefined_set_id, PredefinedSet.dataset_id,
            Dataset.name.label("dataset_name"), PredefinedSet.na_fraction,
            PredefinedSet.created_by, PredefinedSet.created_at, PredefinedSet.is_active,
        )
        .join(Dataset, Dataset.dataset_id == PredefinedSet.dataset_id)
        .order_by(PredefinedSet.predefined_set_id)
    ).mappings().all()
    return [PredefinedSetSummary(**row) for row in rows]


def get_predefined_set(db: Session, predefined_set_id: int) -> PredefinedSetDefinition:
    """Return stored indices, never re-sampling or changing a saved definition."""
    predefined = db.get(PredefinedSet, predefined_set_id)
    if predefined is None:
        raise HTTPException(404, detail="Predefined set was not found.")
    points = db.scalars(
        select(PredefinedSetPoint)
        .where(PredefinedSetPoint.predefined_set_id == predefined_set_id)
        .order_by(PredefinedSetPoint.row_index)
    ).all()
    annotated = sorted(
        (point for point in points if point.annotation_order is not None),
        key=lambda point: point.annotation_order,
    )
    # The physical schema does not enforce uniqueness/completeness of order.
    # Report corruption instead of inventing an order for historical bad rows.
    if [point.annotation_order for point in annotated] != list(range(1, 16)):
        raise HTTPException(500, detail="Stored predefined set has invalid annotation order.")
    return PredefinedSetDefinition(
        predefined_set_id=predefined.predefined_set_id,
        dataset_id=predefined.dataset_id, na_fraction=float(predefined.na_fraction),
        removed_indices=[point.row_index for point in points],
        annotation_indices=[point.row_index for point in annotated],
        created_by=predefined.created_by, created_at=predefined.created_at,
        is_active=predefined.is_active,
    )
