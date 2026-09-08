from io import BytesIO
from types import SimpleNamespace
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.api.inspections import get_ocr_service
from backend.app.core.config import get_settings
from backend.app.core.database import get_db
from backend.app.main import app
from backend.app.models import Base, ComplianceResult, ExtractedField, Inspection, OcrResult
from backend.app.services.ocr import OcrProcessingError


def image_bytes() -> bytes:
    output = BytesIO(); Image.new("RGB", (4, 4), "white").save(output, "PNG"); return output.getvalue()


class SuccessfulOcr:
    def scan(self, _path):
        return SimpleNamespace(engine="PaddleOCR", languages=["en", "hi"], raw_text="Biscuits\nManufactured by: ABC Foods\nMRP Rs 100\nNet Qty: 500g", as_database_detections=lambda: [])


class BrokenOcr:
    def scan(self, _path):
        raise OcrProcessingError("worker timeout")


def test_workflow_is_persisted_idempotent_and_retryable(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path)); get_settings.cache_clear()
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool); Base.metadata.create_all(engine); sessions = sessionmaker(bind=engine)
    def override_db():
        with sessions() as session: yield session
    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_ocr_service] = lambda: SuccessfulOcr()
    try:
        client = TestClient(app)
        inspection = client.post("/api/inspections", json={}).json()
        assert inspection["status"] == "CREATED"
        assert client.post(f"/api/inspections/{inspection['id']}/image", files={"image": ("label.png", image_bytes(), "image/png")}).status_code == 201
        response = client.post(f"/api/inspections/{inspection['id']}/process")
        assert response.status_code == 200
        payload = response.json()
        assert payload["status"] == "COMPLETED" and payload["ocr"]["raw_text"] and payload["extraction"] and payload["compliance"]
        assert payload["extraction"]["fields"]["net_quantity"]["value"] == "500 g"
        quantity = next(finding for finding in payload["compliance"]["findings"] if finding["rule_id"] == "NET_QUANTITY_FORMAT")
        assert quantity["status"] == "PASS" and quantity["value"] == "500 g"
        assert payload["quantity_verification"]["declared_quantity"] == "500 g"
        assert payload["quantity_verification"]["normalized_quantity"] == "500 g"
        assert client.post(f"/api/inspections/{inspection['id']}/process").json() == payload
        with sessions() as session:
            inspection_id = UUID(inspection["id"])
            assert session.get(Inspection, inspection_id).status == "COMPLETED"
            assert session.scalar(select(func.count()).select_from(OcrResult).where(OcrResult.inspection_id == inspection_id)) == 1
            assert session.scalar(select(func.count()).select_from(ExtractedField).where(ExtractedField.inspection_id == inspection_id)) > 0
            assert session.scalar(select(func.count()).select_from(ComplianceResult).where(ComplianceResult.inspection_id == inspection_id)) > 0
        assert client.post(f"/api/inspections/{uuid4()}/process").status_code == 404
        waiting = client.post("/api/inspections", json={}).json()
        assert client.post(f"/api/inspections/{waiting['id']}/process").status_code == 409
    finally:
        app.dependency_overrides.clear(); get_settings.cache_clear(); engine.dispose()


def test_ocr_failure_marks_inspection_failed_and_can_retry(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path)); get_settings.cache_clear()
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool); Base.metadata.create_all(engine); sessions = sessionmaker(bind=engine)
    def override_db():
        with sessions() as session: yield session
    app.dependency_overrides[get_db] = override_db; app.dependency_overrides[get_ocr_service] = lambda: BrokenOcr()
    try:
        client = TestClient(app); inspection = client.post("/api/inspections", json={}).json()
        client.post(f"/api/inspections/{inspection['id']}/image", files={"image": ("label.png", image_bytes(), "image/png")})
        assert client.post(f"/api/inspections/{inspection['id']}/process").status_code == 422
        assert client.get(f"/api/inspections/{inspection['id']}").json()["status"] == "FAILED"
        app.dependency_overrides[get_ocr_service] = lambda: SuccessfulOcr()
        assert client.post(f"/api/inspections/{inspection['id']}/process").json()["status"] == "COMPLETED"
    finally:
        app.dependency_overrides.clear(); get_settings.cache_clear(); engine.dispose()
