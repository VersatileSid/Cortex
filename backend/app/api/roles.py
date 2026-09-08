"""Small protected role-specific dashboard contracts; authorization is server-side."""
from fastapi import APIRouter, Depends
from backend.app.api.auth import require_manufacturer, require_official
from backend.app.models import User

router = APIRouter(prefix="/roles", tags=["roles"])

@router.get("/official", summary="Official dashboard access")
def official_dashboard(user: User = Depends(require_official)) -> dict[str, str]: return {"role": user.role}

@router.get("/manufacturer", summary="Manufacturer dashboard access")
def manufacturer_dashboard(user: User = Depends(require_manufacturer)) -> dict[str, str]: return {"role": user.role}
