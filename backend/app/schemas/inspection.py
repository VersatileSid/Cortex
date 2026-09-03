from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class InspectionCreate(BaseModel):
    manufacturer_id: UUID | None = None
    product_id: UUID | None = None
    notes: str | None = Field(default=None, max_length=5000)


class InspectionCreated(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    inspection_number: str
    status: str
    inspected_at: datetime


class ImageUploaded(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    inspection_id: UUID
    original_filename: str
    content_type: str
    byte_size: int
    created_at: datetime


class OcrDetectionResponse(BaseModel):
    text: str
    confidence: float | None
    bbox: list[list[float]] | None


class OcrProcessed(BaseModel):
    id: UUID
    inspection_id: UUID
    image_id: UUID | None
    engine: str
    processed_at: datetime
    raw_text: str
    results: list[OcrDetectionResponse]
