from datetime import datetime, timezone
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from backend.app.core.config import get_ocr_languages, get_settings
from backend.app.core.database import get_db
from backend.app.models import ExtractedField, Inspection, InspectionImage, OcrResult
from backend.app.schemas.inspection import ExtractionFieldResponse, ExtractionResponse, ImageUploaded, InspectionCreate, InspectionCreated, OcrProcessed
from backend.app.services.extraction import ExtractionService
from backend.app.services.ocr import OcrInitializationError, OcrProcessingError, PaddleOcrService
from backend.app.services.uploads import UploadValidationError, store_image, validate_image

router = APIRouter(prefix="/inspections", tags=["inspections"])


def make_inspection_number() -> str:
    return f"LG-{datetime.now(timezone.utc):%Y%m%d}-{uuid4().hex[:8].upper()}"


def get_ocr_service() -> PaddleOcrService:
    """Dependency factory kept separate so tests and future providers can replace it."""
    return PaddleOcrService(languages=get_ocr_languages())


def get_extraction_service() -> ExtractionService:
    return ExtractionService()


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


@router.post("/{inspection_id}/images/{image_id}/ocr", response_model=OcrProcessed, status_code=status.HTTP_201_CREATED)
def process_inspection_image_ocr(
    inspection_id: UUID,
    image_id: UUID,
    db: Session = Depends(get_db),
    ocr_service: PaddleOcrService = Depends(get_ocr_service),
) -> OcrProcessed:
    inspection = db.get(Inspection, inspection_id)
    if inspection is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Inspection not found.")
    image = db.get(InspectionImage, image_id)
    if image is None or image.inspection_id != inspection.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Inspection image not found.")

    settings = get_settings()
    upload_root = settings.upload_dir.resolve()
    image_path = (upload_root / image.storage_key).resolve()
    if not image_path.is_relative_to(upload_root) or not image_path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Uploaded image file is unavailable.")
    try:
        validate_image(image_path.read_bytes(), image.content_type, settings.max_upload_bytes)
    except UploadValidationError as error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Stored image is invalid.") from error

    try:
        document = ocr_service.scan(image_path)
    except OcrInitializationError as error:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(error)) from error
    except OcrProcessingError as error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error)) from error

    ocr_result = OcrResult(
        inspection_id=inspection.id,
        image_id=image.id,
        engine=document.engine,
        languages=document.languages,
        raw_text=document.raw_text,
        detections=document.as_database_detections(),
    )
    db.add(ocr_result)
    db.commit()
    db.refresh(ocr_result)
    return OcrProcessed(
        id=ocr_result.id,
        inspection_id=ocr_result.inspection_id,
        image_id=ocr_result.image_id,
        engine=ocr_result.engine,
        languages=ocr_result.languages,
        processed_at=ocr_result.created_at,
        raw_text=ocr_result.raw_text,
        results=ocr_result.detections,
    )


@router.post("/{inspection_id}/extract", response_model=ExtractionResponse)
def extract_inspection_information(
    inspection_id: UUID,
    db: Session = Depends(get_db),
    extraction_service: ExtractionService = Depends(get_extraction_service),
) -> ExtractionResponse:
    inspection = db.get(Inspection, inspection_id)
    if inspection is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Inspection not found.")
    ocr_result = db.scalar(
        select(OcrResult).where(OcrResult.inspection_id == inspection.id).order_by(OcrResult.created_at.desc())
    )
    if ocr_result is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="OCR must be run before information extraction.")

    fields = extraction_service.extract(ocr_result.raw_text)
    # Re-running extraction replaces only this interpretation layer, never OCR evidence.
    db.execute(delete(ExtractedField).where(ExtractedField.ocr_result_id == ocr_result.id))
    for field_name, field in fields.items():
        db.add(ExtractedField(
            inspection_id=inspection.id,
            ocr_result_id=ocr_result.id,
            field_name=field_name,
            value=field.value,
            confidence=field.confidence,
            review_status="REVIEW" if field.needs_review else "EXTRACTED",
        ))
    db.commit()
    return ExtractionResponse(
        inspection_id=inspection.id,
        ocr_result_id=ocr_result.id,
        fields={name: ExtractionFieldResponse(**field.__dict__) for name, field in fields.items()},
    )
