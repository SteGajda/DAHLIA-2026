"""Create and inspect predefined sets through the backend connection."""

from fastapi import APIRouter, Depends, Path
from sqlalchemy.orm import Session

from app.api.deps import require_predefined_set_manager
from app.db.session import get_db
from app.models.user import AppUser
from app.schemas.predefined_set import (
    PredefinedSetCreate, PredefinedSetDefinition, PredefinedSetSummary,
)
from app.services.predefined_set_authoring import create_predefined_set
from app.services.predefined_set_catalog import get_predefined_set, list_predefined_sets

router = APIRouter()


@router.get("", response_model=list[PredefinedSetSummary])
def list_sets(
    db: Session = Depends(get_db),
    _user: AppUser = Depends(require_predefined_set_manager),
) -> list[PredefinedSetSummary]:
    return list_predefined_sets(db)


@router.get("/{predefined_set_id}", response_model=PredefinedSetDefinition)
def get_set(
    predefined_set_id: int = Path(gt=0),
    db: Session = Depends(get_db),
    _user: AppUser = Depends(require_predefined_set_manager),
) -> PredefinedSetDefinition:
    return get_predefined_set(db, predefined_set_id)


@router.post("", response_model=PredefinedSetDefinition, status_code=201)
def create_set(
    payload: PredefinedSetCreate,
    db: Session = Depends(get_db),
    user: AppUser = Depends(require_predefined_set_manager),
) -> PredefinedSetDefinition:
    return create_predefined_set(db, payload, user)
