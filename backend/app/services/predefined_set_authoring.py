"""Atomically persist a validated, complete predefined set definition."""

import logging
from decimal import Decimal
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.models.experiment import Dataset, PredefinedSet, PredefinedSetPoint
from app.models.user import AppUser
from app.schemas.predefined_set import PredefinedSetCreate, PredefinedSetDefinition
from app.services.predefined_sets import validate_predefined_points

LOGGER = logging.getLogger(__name__)


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
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, detail="Database constraint conflict; no set was saved.") from exc
    except SQLAlchemyError as exc:
        db.rollback()
        LOGGER.error("Predefined set persistence failed; transaction rolled back.")
        raise HTTPException(500, detail="Predefined set could not be saved.") from exc
