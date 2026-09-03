from io import BytesIO
from uuid import UUID

import pytest
from PIL import Image
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.core.config import get_settings
from backend.app.core.database import get_db
from backend.app.main import app
from backend.app.models import Base, InspectionImage
from backend.app.services.uploads import UploadValidationError, validate_image


def png_bytes() -> bytes:
    image = Image.new("RGB", (4, 4), color="white")
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def test_valid_png_is_accepted() -> None:
    assert validate_image(png_bytes(), "image/png", 1024) == ".png"


def test_invalid_content_is_rejected() -> None:
    with pytest.raises(UploadValidationError, match="not a valid image"):
        validate_image(b"not an image", "image/png", 1024)


def test_image_type_and_size_are_checked() -> None:
    with pytest.raises(UploadValidationError, match="Only JPG"):
        validate_image(png_bytes(), "application/pdf", 1024)
    with pytest.raises(UploadValidationError, match="exceeds"):
        validate_image(png_bytes(), "image/png", 1)


def test_inspection_image_upload_persists_metadata_and_file(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path))
    get_settings.cache_clear()
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    test_session = sessionmaker(bind=engine)

    def override_db():
        with test_session() as session:
            yield session

    app.dependency_overrides[get_db] = override_db
    try:
        client = TestClient(app)
        inspection = client.post("/api/inspections", json={})
        assert inspection.status_code == 201

        response = client.post(
            f"/api/inspections/{inspection.json()['id']}/image",
            files={"image": ("label.png", png_bytes(), "image/png")},
        )
        assert response.status_code == 201
        result = response.json()
        assert result["original_filename"] == "label.png"
        assert result["content_type"] == "image/png"

        with test_session() as session:
            record = session.get(InspectionImage, UUID(result["id"]))
            assert record is not None
            assert (tmp_path / record.storage_key).is_file()
    finally:
        app.dependency_overrides.clear()
        get_settings.cache_clear()
        engine.dispose()
