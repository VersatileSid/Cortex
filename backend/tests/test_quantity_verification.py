import pytest

from backend.app.services.compliance.rule_engine import ComplianceEngine, FieldEvidence
from backend.app.services.quantity_verification import QuantityVerificationService


@pytest.mark.parametrize(("declared", "normalized", "unit"), [
    ("500 g", "500 g", "g"), ("1 kg", "1000 g", "g"),
    ("750 ml", "750 ml", "ml"), ("1 L", "1000 ml", "ml"),
    ("10 N", "10 count", "count"), ("250 cm3", "250 ml", "ml"),
])
def test_declared_quantity_is_structured_without_changing_the_displayed_declaration(declared, normalized, unit):
    verification = QuantityVerificationService().verify(declared, status="PASS", reason="Valid declared quantity.")
    assert verification.declared_quantity == declared
    assert verification.normalized_quantity == normalized
    assert verification.unit == unit
    assert verification.status == "PASS"


@pytest.mark.parametrize("raw", ["", "500 boxes", "about half a kilo"])
def test_missing_or_ambiguous_quantities_do_not_be_presented_as_verified(raw):
    verification = QuantityVerificationService().verify(raw or None)
    assert verification.status == "REVIEW"
    assert verification.normalized_quantity is None


def test_existing_quantity_rule_remains_authoritative_for_invalid_values():
    finding = next(item for item in ComplianceEngine().evaluate({"net_quantity": FieldEvidence("500 boxes", .95)}) if item.rule_id == "NET_QUANTITY_FORMAT")
    verification = QuantityVerificationService().verify("500 boxes", status=finding.status, reason=finding.message, severity=finding.severity)
    assert finding.status == "FAIL"
    assert verification.status == finding.status
