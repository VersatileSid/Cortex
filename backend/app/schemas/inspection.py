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
