"""Atomically persist a validated, complete predefined set definition."""

import logging
from decimal import Decimal
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import select, true, update
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.models.experiment import Dataset, PredefinedSet, PredefinedSetPoint
from app.models.user import AppUser
from app.schemas.predefined_set import PredefinedSetCreate, PredefinedSetDefinition, PredefinedSetStatus
from app.services.predefined_sets import validate_predefined_points

LOGGER = logging.getLogger(__name__)


def deactivate_predefined_set(db: Session, set_id: int) -> PredefinedSetStatus:
    """Idempotently deactivate a definition while retaining all historical data."""
    try:
        dataset_id = db.scalar(select(PredefinedSet.dataset_id).where(
            PredefinedSet.predefined_set_id == set_id,
        ))
        if dataset_id is None:
            raise HTTPException(404, detail="Predefined set was not found.")
        # Use the same lock order as creation and its active-duplicate check.
        db.execute(select(Dataset.dataset_id).where(Dataset.dataset_id == dataset_id)
                   .with_hint(Dataset, "WITH (UPDLOCK, HOLDLOCK)", dialect_name="mssql")).one()
        db.execute(update(PredefinedSet).where(PredefinedSet.predefined_set_id == set_id)
                   .values(is_active=False))
        db.commit()
        return PredefinedSetStatus(predefined_set_id=set_id, is_active=False)
    except HTTPException:
        db.rollback()
        raise
    except SQLAlchemyError as exc:
        db.rollback()
        LOGGER.error("Predefined set deactivation failed; transaction rolled back.")
        raise HTTPException(500, detail="Predefined set deactivation could not be confirmed. Refresh the catalog before retrying.") from exc


def create_predefined_set(
    db: Session, payload: PredefinedSetCreate, user: AppUser,
) -> PredefinedSetDefinition:
    """Save one new active set; no existing definition is edited.

    Authorization is enforced by the API dependency. Only dataset metadata is
    read, since row positions refer to an immutable central dataset. The caller
    supplies the final 15-point order, including any prior preview random draw.
    """
    dataset = db.execute(
        select(Dataset.dataset_id, Dataset.row_count, Dataset.is_active)
        .where(Dataset.dataset_id == payload.dataset_id)
        # Serialize creation for this dataset until commit/rollback on SQL Server.
        # Concurrent requests must not both pass the duplicate check.
        .with_hint(Dataset, "WITH (UPDLOCK, HOLDLOCK)", dialect_name="mssql")
    ).one_or_none()
    if dataset is None:
        raise HTTPException(404, detail="Dataset was not found.")
    if not dataset.is_active:
        raise HTTPException(409, detail="Cannot create a set for an inactive dataset.")
    try:
        points = validate_predefined_points(
            row_count=dataset.row_count, na_fraction=payload.na_fraction,
            removed_indices=payload.removed_indices,
            annotation_indices=payload.annotation_indices,
        )
    except ValueError as exc:
        raise HTTPException(422, detail=str(exc)) from exc

    try:
        expected = {index: None for index in points.removed_indices}
        expected.update({index: order for order, index in
                         enumerate(points.annotation_indices, start=1)})
        candidates: dict[int, dict[int, int | None]] = {}
        rows = db.execute(
            select(PredefinedSet.predefined_set_id, PredefinedSetPoint.row_index,
                   PredefinedSetPoint.annotation_order)
            .join(PredefinedSetPoint,
                  PredefinedSetPoint.predefined_set_id == PredefinedSet.predefined_set_id)
            .where(PredefinedSet.dataset_id == dataset.dataset_id,
                   PredefinedSet.na_fraction == Decimal(str(payload.na_fraction)),
                   PredefinedSet.is_active == true())
            .order_by(PredefinedSet.predefined_set_id)
        )
        for set_id, row_index, annotation_order in rows:
            candidates.setdefault(set_id, {})[row_index] = annotation_order
        for set_id, definition in candidates.items():
            if definition == expected:
                raise HTTPException(409, detail=f"An identical active set already exists: Set #{set_id}.")
        predefined = PredefinedSet(
            # The existing schema requires a unique, nonempty name before the
            # identity is allocated. This temporary value is never committed.
            name=f"pending:{uuid4().hex}", dataset_id=dataset.dataset_id,
            na_fraction=Decimal(str(payload.na_fraction)),
            created_by=user.user_id, is_active=True,
        )
        db.add(predefined)
        db.flush()
        predefined.name = f"Set #{predefined.predefined_set_id}"
        orders = {index: order for order, index in
                  enumerate(points.annotation_indices, start=1)}
        db.add_all([
            PredefinedSetPoint(
                predefined_set_id=predefined.predefined_set_id,
                row_index=index, annotation_order=orders.get(index),
            )
            for index in sorted(points.removed_indices)
        ])
        db.flush()
        result = PredefinedSetDefinition(
            predefined_set_id=predefined.predefined_set_id,
            dataset_id=predefined.dataset_id, na_fraction=payload.na_fraction,
            removed_indices=sorted(points.removed_indices),
            annotation_indices=list(points.annotation_indices),
            created_by=predefined.created_by, created_at=predefined.created_at,
            is_active=predefined.is_active,
        )
        db.commit()
        return result
    except HTTPException:
        db.rollback()
        raise
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, detail="Database constraint conflict; no set was saved.") from exc
    except SQLAlchemyError as exc:
        db.rollback()
        LOGGER.error("Predefined set persistence failed; transaction rolled back.")
        raise HTTPException(500, detail="Predefined set could not be saved.") from exc
