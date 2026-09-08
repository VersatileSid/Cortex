"""Official-only, compact risk prioritisation queue."""
from math import ceil
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from backend.app.api.auth import require_official
from backend.app.core.config import get_settings
from backend.app.core.database import get_db
from backend.app.models import User
from backend.app.schemas.inspection import RiskTargetingPage, RiskTargetingItem
from backend.app.services.risk import RiskService

router = APIRouter(prefix="/risk-targeting", tags=["risk-targeting"])

@router.get("", response_model=RiskTargetingPage)
def list_risk_targeting(
    page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
    risk_level: str | None = Query(None, max_length=20), compliance_status: str | None = Query(None, max_length=20),
    search: str | None = Query(None, max_length=255), db: Session = Depends(get_db), user: User = Depends(require_official),
) -> RiskTargetingPage:
    rows = RiskService(db, get_settings().pattern_min_occurrences).for_user(user.id)
    if risk_level: rows = [row for row in rows if row[2].risk_level == risk_level.upper()]
    if compliance_status: rows = [row for row in rows if row[3] == compliance_status.upper()]
    if search and (term := search.strip().lower()): rows = [row for row in rows if term in (row[1] or "").lower() or term in row[0].inspection_number.lower()]
    total = len(rows); start = (page - 1) * page_size
    items = []
    for index, (inspection, product_name, assessment, status_value) in enumerate(rows[start:start + page_size], start=start + 1):
        primary = assessment.reasons[0].description if assessment.reasons else "No adverse evidence recorded."
        items.append(RiskTargetingItem(inspection_id=inspection.id, product_name=product_name, risk_score=assessment.risk_score, risk_level=assessment.risk_level, compliance_status=status_value, primary_reason=primary, completed_at=inspection.completed_at or inspection.created_at, priority=index))
    counts = {level: sum(row[2].risk_level == level for row in rows) for level in ("CRITICAL", "HIGH", "MEDIUM", "LOW")}
    return RiskTargetingPage(items=items, total=total, page=page, page_size=page_size, total_pages=ceil(total / page_size) if total else 0, summary=counts)
