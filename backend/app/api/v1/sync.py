"""Manual upload endpoint for completed desktop experiments."""

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.api.deps import get_verified_user
from app.db.session import get_db
from app.models.user import AppUser
from app.schemas.experiment import CompletedExperiment
from app.services.synchronization import synchronize

router = APIRouter()


@router.post('/experiment', status_code=201)
def sync_experiment(
    payload: CompletedExperiment, response: Response,
    db: Session = Depends(get_db), user: AppUser = Depends(get_verified_user),
):
    result, created = synchronize(db, payload, user)
    response.status_code = 201 if created else 200
    return result
