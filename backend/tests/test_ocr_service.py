from pathlib import Path
from io import BytesIO
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.api.inspections import get_ocr_service
from backend.app.core.config import Settings, get_ocr_languages, get_settings
from backend.app.core.database import get_db
from backend.app.main import app
from backend.app.models import Base, OcrResult
from backend.app.services.ocr import OcrDetection, OcrDocument
from backend.app.services.ocr import PaddleOcrService


class LegacyEngine:
    def ocr(self, image_path: str, cls: bool):
        assert cls is True
        assert image_path.endswith("package.png")
        return [[[[[1, 2], [3, 2], [3, 4], [1, 4]], ("MRP Rs 50", 0.96)]]]


def test_ocr_service_accepts_an_injected_engine() -> None:
    service = PaddleOcrService(engine=LegacyEngine())
    document = service._run_engine(service._get_engine("en"), Path("package.png"))

    assert document[0].text == "MRP Rs 50"
    assert document[0].confidence == 0.96
    assert document[0].bbox == [[1.0, 2.0], [3.0, 2.0], [3.0, 4.0], [1.0, 4.0]]


def test_v3_prediction_parser_preserves_text_score_and_box() -> None:
    predictions = [{"res": {"rec_texts": ["Batch 10"], "rec_scores": [0.91], "dt_polys": [[[0, 0], [5, 0], [5, 2], [0, 2]]]}}]

    result = PaddleOcrService._parse_v3_predictions(predictions)

    assert result[0].text == "Batch 10"
    assert result[0].confidence == 0.91


def test_english_and_hindi_are_default_configured_languages() -> None:
    assert get_ocr_languages(Settings(ocr_languages="en,hi")) == ("en", "hi")


def test_duplicate_multilingual_detections_keep_best_confidence() -> None:
    duplicate_box = [[0.0, 0.0], [5.0, 0.0], [5.0, 2.0], [0.0, 2.0]]
    detections = PaddleOcrService._deduplicate([
        OcrDetection("MRP", 0.83, duplicate_box),
        OcrDetection("MRP", 0.96, duplicate_box),
        OcrDetection("मूल्य", 0.91, duplicate_box),
    ])

    assert len(detections) == 2
    assert next(item for item in detections if item.text == "MRP").confidence == 0.96


def png_bytes() -> bytes:
    image = Image.new("RGB", (4, 4), color="white")
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


class FakeOcrService:
    def scan(self, image_path: Path) -> OcrDocument:
        assert image_path.is_file()
        return OcrDocument(
            engine="PaddleOCR",
            languages=["en", "hi"],
            detections=[OcrDetection(text="MRP Rs 50", confidence=0.96, bbox=[[1, 2], [3, 2], [3, 4], [1, 4]])],
        )


def test_ocr_endpoint_stores_real_service_output(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path))
    get_settings.cache_clear()
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine)

    def override_db():
        with sessions() as session:
            yield session

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_ocr_service] = lambda: FakeOcrService()
    try:
        client = TestClient(app)
        inspection = client.post("/api/inspections", json={}).json()
        uploaded = client.post(
            f"/api/inspections/{inspection['id']}/image",
            files={"image": ("label.png", png_bytes(), "image/png")},
        ).json()

        response = client.post(f"/api/inspections/{inspection['id']}/images/{uploaded['id']}/ocr")

        assert response.status_code == 201
        assert response.json()["languages"] == ["en", "hi"]
        assert response.json()["results"][0]["text"] == "MRP Rs 50"
        with sessions() as session:
            stored = session.scalar(select(OcrResult).where(OcrResult.id == UUID(response.json()["id"])))
            assert stored is not None
            assert stored.raw_text == "MRP Rs 50"
            assert stored.detections[0]["confidence"] == 0.96
    finally:
        app.dependency_overrides.clear()
        get_settings.cache_clear()
        engine.dispose()


def test_ocr_endpoint_reports_missing_inspection_and_image(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path))
    get_settings.cache_clear()
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine)

    def override_db():
        with sessions() as session:
            yield session

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_ocr_service] = lambda: FakeOcrService()
    try:
        client = TestClient(app)
        missing_inspection = client.post(f"/api/inspections/{uuid4()}/images/{uuid4()}/ocr")
        assert missing_inspection.status_code == 404

        inspection = client.post("/api/inspections", json={}).json()
        missing_image = client.post(f"/api/inspections/{inspection['id']}/images/{uuid4()}/ocr")
        assert missing_image.status_code == 404
    finally:
        app.dependency_overrides.clear()
        get_settings.cache_clear()
        engine.dispose()


def test_ocr_endpoint_rejects_a_tampered_stored_image(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path))
    get_settings.cache_clear()
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine)

    def override_db():
        with sessions() as session:
            yield session

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_ocr_service] = lambda: FakeOcrService()
    try:
        client = TestClient(app)
        inspection = client.post("/api/inspections", json={}).json()
        uploaded = client.post(
            f"/api/inspections/{inspection['id']}/image",
            files={"image": ("label.png", png_bytes(), "image/png")},
        ).json()
        with sessions() as session:
            stored = session.get(OcrResult, uuid4())
            assert stored is None
        image_files = list(tmp_path.glob("*.png"))
        image_files[0].write_bytes(b"not an image")

        response = client.post(f"/api/inspections/{inspection['id']}/images/{uploaded['id']}/ocr")
        assert response.status_code == 422
    finally:
        app.dependency_overrides.clear()
        get_settings.cache_clear()
        engine.dispose()
