"""Reliable orchestration for the persisted inspection lifecycle."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.models import ComplianceResult, ComplianceRule, ExtractedField, Inspection, InspectionImage, OcrResult
from backend.app.schemas.inspection import ComplianceFindingResponse, ComplianceResponse, ComplianceSummary, ExtractionFieldResponse, ExtractionResponse, ImageUploaded, InspectionSummary, OcrProcessed
from backend.app.services.compliance.rule_engine import ComplianceEngine, FieldEvidence, RULES
from backend.app.services.extraction.extraction_service import ExtractionService
from backend.app.services.ocr.ocr_service import OcrInitializationError, OcrProcessingError, PaddleOcrService
from backend.app.services.uploads import UploadValidationError, validate_image

logger = logging.getLogger("uvicorn.error")


class WorkflowError(Exception):
    def __init__(self, stage: str, message: str, status_code: int = 422):
        self.stage, self.message, self.status_code = stage, message, status_code
        super().__init__(message)


class InspectionWorkflow:
    def __init__(self, db: Session, ocr: PaddleOcrService, extraction: ExtractionService, compliance: ComplianceEngine, upload_dir: Path, max_upload_bytes: int):
        self.db, self.ocr, self.extraction, self.compliance = db, ocr, extraction, compliance
        self.upload_dir, self.max_upload_bytes = upload_dir, max_upload_bytes

    def _set_status(self, inspection: Inspection, status: str) -> None:
        inspection.status = status
        inspection.failure_stage = None
        inspection.failure_message = None
        self.db.commit()

    def _fail(self, inspection: Inspection, stage: str, error: Exception) -> WorkflowError:
        # Diagnostic detail remains in server logs; the persisted message is safe to show.
        logger.exception("Inspection workflow failed inspection_id=%s stage=%s", inspection.id, stage)
        inspection.status, inspection.failure_stage = "FAILED", stage
        inspection.failure_message = f"{stage.title()} could not be completed. Please retry the inspection."
        self.db.commit()
        return WorkflowError(stage, inspection.failure_message, 503 if isinstance(error, OcrInitializationError) else 422)

    @staticmethod
    def _rules(db: Session) -> dict[str, ComplianceRule]:
        existing = {rule.rule_code: rule for rule in db.scalars(select(ComplianceRule)).all()}
        for code, name, target_field, severity in RULES:
            if code not in existing:
                rule = ComplianceRule(rule_code=code, description=f"{name}. Deterministic extraction-evidence check; it is not a legal determination.", target_field=target_field, severity=severity, enabled=True, configuration={})
                db.add(rule); existing[code] = rule
        db.flush()
        return existing

    def process(self, inspection_id: UUID) -> InspectionSummary:
        inspection = self.db.get(Inspection, inspection_id)
        if inspection is None:
            raise KeyError("Inspection not found.")
        image = self.db.scalar(select(InspectionImage).where(InspectionImage.inspection_id == inspection.id).order_by(InspectionImage.created_at.desc()))
        if image is None:
            raise WorkflowError("image", "Upload a package-label image before processing.", 409)
        if inspection.status == "COMPLETED":
            return self.summary(inspection.id)

        ocr_result = self.db.scalar(select(OcrResult).where(OcrResult.inspection_id == inspection.id, OcrResult.image_id == image.id).order_by(OcrResult.created_at.desc()))
        if ocr_result is None:
            self._set_status(inspection, "OCR_PROCESSING")
            path = (self.upload_dir.resolve() / image.storage_key).resolve()
            try:
                if not path.is_relative_to(self.upload_dir.resolve()) or not path.is_file():
                    raise FileNotFoundError("Uploaded image is unavailable")
                validate_image(path.read_bytes(), image.content_type, self.max_upload_bytes)
                document = self.ocr.scan(path)
                ocr_result = OcrResult(inspection_id=inspection.id, image_id=image.id, engine=document.engine, languages=document.languages, raw_text=document.raw_text, detections=document.as_database_detections())
                self.db.add(ocr_result); self.db.commit(); self.db.refresh(ocr_result)
            except (OcrInitializationError, OcrProcessingError, UploadValidationError, OSError) as error:
                raise self._fail(inspection, "OCR", error) from error
        self._set_status(inspection, "OCR_COMPLETED")

        extracted = self.db.scalars(select(ExtractedField).where(ExtractedField.ocr_result_id == ocr_result.id)).all()
        if not extracted:
            self._set_status(inspection, "EXTRACTION_PROCESSING")
            try:
                values = self.extraction.extract(ocr_result.raw_text)
                for name, value in values.items():
                    self.db.add(ExtractedField(inspection_id=inspection.id, ocr_result_id=ocr_result.id, field_name=name, value=value.value, confidence=value.confidence, review_status="REVIEW" if value.needs_review else "EXTRACTED"))
                self.db.commit()
            except Exception as error:
                self.db.rollback()
                raise self._fail(inspection, "extraction", error) from error
            extracted = self.db.scalars(select(ExtractedField).where(ExtractedField.ocr_result_id == ocr_result.id)).all()
        self._set_status(inspection, "EXTRACTION_COMPLETED")

        persisted = self.db.scalars(select(ComplianceResult).where(ComplianceResult.inspection_id == inspection.id)).all()
        if not persisted:
            self._set_status(inspection, "COMPLIANCE_PROCESSING")
            try:
                fields = {field.field_name: FieldEvidence(field.value, float(field.confidence) if field.confidence is not None else None, field.review_status == "REVIEW", field.value) for field in extracted}
                rules = self._rules(self.db)
                for finding in self.compliance.evaluate(fields):
                    rule = rules.get(finding.rule_id)
                    if rule and rule.enabled:
                        self.db.add(ComplianceResult(inspection_id=inspection.id, rule_id=rule.id, result=finding.status, explanation=finding.message, field_name=finding.field, value=finding.value, confidence=finding.confidence, evidence=finding.evidence))
                self.db.commit()
            except Exception as error:
                self.db.rollback()
                raise self._fail(inspection, "compliance", error) from error
        inspection.status, inspection.completed_at = "COMPLETED", datetime.now(timezone.utc)
        inspection.failure_stage = inspection.failure_message = None
        self.db.commit()
        return self.summary(inspection.id)

    def summary(self, inspection_id: UUID) -> InspectionSummary:
        inspection = self.db.get(Inspection, inspection_id)
        if inspection is None:
            raise KeyError("Inspection not found.")
        image = self.db.scalar(select(InspectionImage).where(InspectionImage.inspection_id == inspection.id).order_by(InspectionImage.created_at.desc()))
        ocr = self.db.scalar(select(OcrResult).where(OcrResult.inspection_id == inspection.id).order_by(OcrResult.created_at.desc()))
        extracted = self.db.scalars(select(ExtractedField).where(ExtractedField.ocr_result_id == ocr.id)).all() if ocr else []
        results = self.db.scalars(select(ComplianceResult).where(ComplianceResult.inspection_id == inspection.id).join(ComplianceRule).order_by(ComplianceRule.rule_code)).all()
        ocr_response = OcrProcessed(id=ocr.id, inspection_id=ocr.inspection_id, image_id=ocr.image_id, engine=ocr.engine, languages=ocr.languages, processed_at=ocr.created_at, raw_text=ocr.raw_text, results=ocr.detections) if ocr else None
        extraction_response = ExtractionResponse(inspection_id=inspection.id, ocr_result_id=ocr.id, fields={field.field_name: ExtractionFieldResponse(value=field.value, confidence=float(field.confidence or 0), needs_review=field.review_status == "REVIEW") for field in extracted}) if ocr and extracted else None
        findings = [ComplianceFindingResponse(rule_id=result.rule.rule_code, rule_name=result.rule.description.split(".", 1)[0], status=result.result, severity=result.rule.severity, message=result.explanation, field=result.field_name, value=result.value, confidence=float(result.confidence) if result.confidence is not None else None, evidence=result.evidence) for result in results]
        counts = {value: sum(f.status == value for f in findings) for value in ("PASS", "FAIL", "REVIEW")}
        compliance_response = ComplianceResponse(inspection_id=inspection.id, overall_status="FAIL" if counts["FAIL"] else "REVIEW" if counts["REVIEW"] else "PASS", summary=ComplianceSummary(passed=counts["PASS"], failed=counts["FAIL"], review=counts["REVIEW"]), findings=findings) if results else None
        return InspectionSummary(id=inspection.id, inspection_number=inspection.inspection_number, status=inspection.status, created_at=inspection.created_at, updated_at=inspection.updated_at, completed_at=inspection.completed_at, failure_stage=inspection.failure_stage, failure_message=inspection.failure_message, image=ImageUploaded.model_validate(image) if image else None, ocr=ocr_response, extraction=extraction_response, compliance=compliance_response)
