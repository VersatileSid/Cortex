from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.core.database import get_db
from backend.app.main import app
from backend.app.models import Base, ComplianceResult, ExtractedField, OcrResult


def test_extract_endpoint_returns_and_persists_deterministic_fields() -> None:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine)

    def override_db():
        with sessions() as session:
            yield session

    app.dependency_overrides[get_db] = override_db
    try:
        client = TestClient(app)
        inspection = client.post("/api/inspections", json={}).json()
        with sessions() as session:
            ocr = OcrResult(inspection_id=UUID(inspection["id"]), raw_text="Manufactured by: ABC Foods\nMRP ₹100\nNet Qty: 500g", languages=["en"], detections=[])
            session.add(ocr)
            session.commit()
            ocr_id = ocr.id
        response = client.post(f"/api/inspections/{inspection['id']}/extract")
        assert response.status_code == 200
        payload = response.json()
        assert payload["ocr_result_id"] == str(ocr_id)
        assert payload["fields"]["manufacturer"]["value"] == "ABC Foods"
        assert payload["fields"]["mrp"]["value"] == "₹100"
        assert {"value", "confidence", "needs_review"} <= payload["fields"]["net_quantity"].keys()
        with sessions() as session:
            assert session.scalar(select(ExtractedField).where(ExtractedField.ocr_result_id == ocr_id)) is not None
            assert session.get(OcrResult, ocr_id).raw_text == "Manufactured by: ABC Foods\nMRP ₹100\nNet Qty: 500g"
        assert client.post(f"/api/inspections/{inspection['id']}/extract").status_code == 200
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def test_extract_endpoint_reports_missing_inspection_and_ocr() -> None:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine)

    def override_db():
        with sessions() as session:
            yield session

    app.dependency_overrides[get_db] = override_db
    try:
        client = TestClient(app)
        assert client.post(f"/api/inspections/{uuid4()}/extract").status_code == 404
        inspection = client.post("/api/inspections", json={}).json()
        response = client.post(f"/api/inspections/{inspection['id']}/extract")
        assert response.status_code == 409
        assert "OCR" in response.json()["detail"]
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def test_reextract_invalidates_stale_compliance_findings() -> None:
    """A report must never render the previous parse's result after re-extraction."""
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine)

    def override_db():
        with sessions() as session:
            yield session

    app.dependency_overrides[get_db] = override_db
    try:
        client = TestClient(app)
        inspection = client.post("/api/inspections", json={}).json()
        with sessions() as session:
            ocr = OcrResult(inspection_id=UUID(inspection["id"]), raw_text="Net Qty: 500 boxes", languages=["en"], detections=[])
            session.add(ocr)
            session.commit()
            ocr_id = ocr.id
        assert client.post(f"/api/inspections/{inspection['id']}/extract").status_code == 200
        assert client.post(f"/api/inspections/{inspection['id']}/compliance").status_code == 200
        with sessions() as session:
            session.get(OcrResult, ocr_id).raw_text = "Net Qty: 0.5 KG"
            session.commit()
        response = client.post(f"/api/inspections/{inspection['id']}/extract")
        assert response.status_code == 200
        assert response.json()["fields"]["net_quantity"]["value"] == "500 g"
        with sessions() as session:
            assert session.query(ComplianceResult).filter_by(inspection_id=UUID(inspection["id"])).count() == 0
        fresh = client.post(f"/api/inspections/{inspection['id']}/compliance").json()
        quantity = next(finding for finding in fresh["findings"] if finding["rule_id"] == "NET_QUANTITY_FORMAT")
        assert quantity["status"] == "PASS" and quantity["value"] == "500 g"
    finally:
        app.dependency_overrides.clear()
        engine.dispose()
