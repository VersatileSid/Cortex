from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from backend.app.api.auth import get_current_user
from backend.app.core.config import get_settings
from backend.app.core.database import get_db
from backend.app.models import User
from backend.app.schemas.inspection import PatternResponse
from backend.app.services.patterns import PatternService

router = APIRouter(prefix="/patterns", tags=["patterns"], dependencies=[Depends(get_current_user)])


@router.get("", response_model=list[PatternResponse], summary="List repeat patterns for the authenticated user")
def list_patterns(pattern_type: str | None = Query(None), severity: str | None = Query(None), search: str | None = Query(None, max_length=255), db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> list[PatternResponse]:
    return PatternService(db, get_settings().pattern_min_occurrences).for_user(user.id, pattern_type, severity, search)
