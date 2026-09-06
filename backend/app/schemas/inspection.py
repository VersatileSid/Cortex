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
    languages: list[str]
    processed_at: datetime
    raw_text: str
    results: list[OcrDetectionResponse]


class ExtractionFieldResponse(BaseModel):
    value: str | None = None
    confidence: float = Field(ge=0.0, le=1.0)
    needs_review: bool
    source_text: str | None = None
    matched_pattern: str | None = None
    normalized_value: str | None = None


class ExtractionResponse(BaseModel):
    inspection_id: UUID
    ocr_result_id: UUID
    fields: dict[str, ExtractionFieldResponse]


class ComplianceSummary(BaseModel):
    passed: int
    failed: int
    review: int


class ComplianceFindingResponse(BaseModel):
    rule_id: str
    rule_name: str
    status: str
    severity: str
    message: str
    field: str | None = None
    value: str | None = None
    confidence: float | None = None
    evidence: str | None = None


class ComplianceResponse(BaseModel):
    inspection_id: UUID
    overall_status: str
    summary: ComplianceSummary
    findings: list[ComplianceFindingResponse]
