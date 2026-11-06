"""Read predefined set metadata and persisted point order for managers."""

import base64
import hashlib
import json

from fastapi import HTTPException
from sqlalchemy import select, true, text
from sqlalchemy.orm import Session

from app.models.experiment import Dataset, PredefinedSet, PredefinedSetPoint
from app.schemas.predefined_set import AvailablePredefinedSet, PredefinedSetDefinition, PredefinedSetSummary, PredefinedSetExecution


def get_catalog_id(db: Session) -> str:
    """Separate local SQL Server and Azure catalogs without exposing connection secrets."""
    if db.get_bind().dialect.name == "mssql":
        identity = list(db.execute(text("SELECT CONVERT(nvarchar(128), SERVERPROPERTY('ServerName')), DB_NAME()")).one())
    else:
        identity = [db.get_bind().url.render_as_string(hide_password=True)]
    return hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()


def get_execution_set(db: Session, set_id: int) -> PredefinedSetExecution:
    predefined = db.get(PredefinedSet, set_id)
    if predefined is None:
        raise HTTPException(404, detail="Predefined set was not found.")
    dataset = db.get(Dataset, predefined.dataset_id)
    if not predefined.is_active or dataset is None or not dataset.is_active:
        raise HTTPException(409, detail="This set or its dataset is inactive. Refresh the catalog.")
    definition = get_predefined_set(db, set_id)
    content = bytes(dataset.csv_file)
    if hashlib.sha256(content).digest() != bytes(dataset.csv_sha256):
        raise HTTPException(500, detail="Central dataset checksum validation failed.")
    return PredefinedSetExecution(
        catalog_id=get_catalog_id(db),
        predefined_set_id=set_id, dataset_id=dataset.dataset_id, dataset_name=dataset.name,
        na_fraction=definition.na_fraction, removed_indices=definition.removed_indices,
        annotation_indices=definition.annotation_indices, row_count=dataset.row_count,
        csv_base64=base64.b64encode(content).decode("ascii"), csv_sha256=bytes(dataset.csv_sha256).hex(),
        imputed_column=dataset.imputed_column, target_column=dataset.target_column,
        reference_columns=json.loads(dataset.reference_columns_json),
        categorical_columns=json.loads(dataset.categorical_columns_json), precision=float(dataset.precision_value),
    )


def list_available_predefined_sets(db: Session) -> list[AvailablePredefinedSet]:
    """Offer only active definitions belonging to active datasets."""
    rows = db.execute(select(
        PredefinedSet.predefined_set_id, PredefinedSet.dataset_id,
        Dataset.name.label("dataset_name"), PredefinedSet.na_fraction,
    ).join(Dataset, Dataset.dataset_id == PredefinedSet.dataset_id)
      .where(PredefinedSet.is_active == true(), Dataset.is_active == true())
      .order_by(PredefinedSet.predefined_set_id)).mappings().all()
    return [AvailablePredefinedSet(**row) for row in rows]


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
