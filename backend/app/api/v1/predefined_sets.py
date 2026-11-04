"""Create predefined sets through the backend's database connection."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import require_predefined_set_manager
from app.db.session import get_db
from app.models.user import AppUser
from app.schemas.predefined_set import PredefinedSetCreate, PredefinedSetDefinition
from app.services.predefined_set_authoring import create_predefined_set

router = APIRouter()


@router.post("", response_model=PredefinedSetDefinition, status_code=201)
def create_set(
    payload: PredefinedSetCreate,
    db: Session = Depends(get_db),
    user: AppUser = Depends(require_predefined_set_manager),
) -> PredefinedSetDefinition:
    return create_predefined_set(db, payload, user)
