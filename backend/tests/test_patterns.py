from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.api.auth import get_current_user
from backend.app.core.database import get_db
from backend.app.main import app
from backend.app.models import Base, ComplianceResult, ComplianceRule, ExtractedField, Inspection, User

USER_A = UUID("00000000-0000-0000-0000-000000000101")
USER_B = UUID("00000000-0000-0000-0000-000000000102")


def _inspection(user_id, number, when, status="COMPLETED"):
    return Inspection(id=uuid4(), user_id=user_id, inspection_number=number, status=status, inspected_at=when, completed_at=when)


def test_patterns_are_owned_grouped_filtered_and_ordered() -> None:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool); Base.metadata.create_all(engine); sessions = sessionmaker(bind=engine)
    now = datetime.now(timezone.utc)
    with sessions() as db:
        rule_a = ComplianceRule(rule_code="MISSING_FSSAI", description="Missing FSSAI information. Required information was absent.", target_field="fssai", severity="HIGH", enabled=True, configuration={})
        rule_b = ComplianceRule(rule_code="MRP_FORMAT", description="MRP format. Invalid MRP.", target_field="mrp", severity="WARNING", enabled=True, configuration={})
        db.add_all([rule_a, rule_b]); db.flush()
        a1, a2, a3 = (_inspection(USER_A, f"A-{i}", now + timedelta(days=i)) for i in range(3))
        b1, b2 = (_inspection(USER_B, f"B-{i}", now + timedelta(days=i)) for i in range(2))
        incomplete = _inspection(USER_A, "A-open", now, "OCR_COMPLETED")
        db.add_all([a1, a2, a3, b1, b2, incomplete]); db.flush()
        db.add_all([
            ComplianceResult(inspection_id=a1.id, rule_id=rule_a.id, result="FAIL", explanation="message one"), ComplianceResult(inspection_id=a2.id, rule_id=rule_a.id, result="FAIL", explanation="message two"), ComplianceResult(inspection_id=a3.id, rule_id=rule_b.id, result="REVIEW", explanation="warning"),
            ComplianceResult(inspection_id=b1.id, rule_id=rule_a.id, result="FAIL", explanation="other user"), ComplianceResult(inspection_id=b2.id, rule_id=rule_a.id, result="FAIL", explanation="other user"), ComplianceResult(inspection_id=incomplete.id, rule_id=rule_a.id, result="FAIL", explanation="not complete"),
            ExtractedField(inspection_id=a1.id, field_name="net_quantity", value=None, review_status="REVIEW"), ExtractedField(inspection_id=a2.id, field_name="net_quantity", value=None, review_status="REVIEW"),
        ]); db.commit()
    def override_db():
        with sessions() as db: yield db
    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = lambda: User(id=USER_A, username="a", email="a@example.test", full_name="A", password_hash="x", is_active=True)
    try:
        client = TestClient(app); payload = client.get("/api/patterns").json()
        assert [item["pattern_key"] for item in payload] == ["MISSING_FSSAI", "MISSING_FIELD:net_quantity"]
        violation = payload[0]
        assert violation["occurrence_count"] == 2 and violation["severity"] == "HIGH" and len(violation["inspection_ids"]) == 2
        assert violation["first_seen"] < violation["last_seen"]
        assert client.get("/api/patterns?pattern_type=COMPLIANCE_VIOLATION").json()[0]["pattern_key"] == "MISSING_FSSAI"
        assert client.get("/api/patterns?severity=WARNING").json()[0]["pattern_type"] == "MISSING_FIELD"
        assert client.get("/api/patterns?search=quantity").json()[0]["pattern_key"] == "MISSING_FIELD:net_quantity"
    finally:
        app.dependency_overrides.clear(); engine.dispose()


def test_patterns_require_authentication() -> None:
    app.dependency_overrides[get_current_user] = lambda: (_ for _ in ()).throw(HTTPException(status_code=401, detail="Not authenticated."))
    try:
        assert TestClient(app).get("/api/patterns").status_code == 401
    finally:
        app.dependency_overrides.clear()
