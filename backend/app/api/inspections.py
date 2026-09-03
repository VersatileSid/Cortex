from datetime import datetime, timezone
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from backend.app.core.config import get_settings
from backend.app.core.database import get_db
from backend.app.models import Inspection, InspectionImage
from backend.app.schemas.inspection import ImageUploaded, InspectionCreate, InspectionCreated
from backend.app.services.uploads import UploadValidationError, store_image, validate_image

router = APIRouter(prefix="/inspections", tags=["inspections"])


def make_inspection_number() -> str:
    return f"LG-{datetime.now(timezone.utc):%Y%m%d}-{uuid4().hex[:8].upper()}"


@router.post("", response_model=InspectionCreated, status_code=status.HTTP_201_CREATED)
def create_inspection(payload: InspectionCreate, db: Session = Depends(get_db)) -> Inspection:
    inspection = Inspection(
        inspection_number=make_inspection_number(),
        manufacturer_id=payload.manufacturer_id,
        product_id=payload.product_id,
        notes=payload.notes,
    )
    db.add(inspection)
    db.commit()
    db.refresh(inspection)
    return inspection


@router.post("/{inspection_id}/image", response_model=ImageUploaded, status_code=status.HTTP_201_CREATED)
async def upload_inspection_image(
    inspection_id: UUID,
    image: UploadFile = File(..., description="Package image in JPG, JPEG, or PNG format."),
    db: Session = Depends(get_db),
) -> InspectionImage:
    inspection = db.get(Inspection, inspection_id)
    if inspection is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Inspection not found.")

    settings = get_settings()
    content = await image.read(settings.max_upload_bytes + 1)
    content_type = (image.content_type or "").lower()
    try:
        validate_image(content, content_type, settings.max_upload_bytes)
        stored = store_image(content, image.filename or "package-image", content_type, settings.upload_dir)
    except UploadValidationError as error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)) from error

    image_record = InspectionImage(inspection_id=inspection.id, **stored.__dict__)
    db.add(image_record)
    db.commit()
    db.refresh(image_record)
    return image_record
