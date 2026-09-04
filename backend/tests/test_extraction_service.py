import pytest

from backend.app.services.extraction import ExtractionService


@pytest.fixture
def service() -> ExtractionService:
    return ExtractionService()


def test_extracts_complete_english_label(service: ExtractionService) -> None:
    fields = service.extract("""Sunshine Biscuits
Manufactured by: ABC Foods Pvt Ltd
123 Industrial Area, New Delhi - 110001
Packed by: XYZ Packaging Ltd
Imported by: Example Imports Pvt Ltd
MRP: Rs. 100
Net Quantity: 500g
Mfg: 08/2026
Packed On: 15/08/2026
Best Before: 6 Months
Use By: 08/2027
Expiry: 12/2027
Customer Care: 1800-123-4567
care@example.com
www.example.com""")
    assert fields["manufacturer"].value == "ABC Foods Pvt Ltd"
    assert fields["manufacturer_address"].value == "123 Industrial Area, New Delhi - 110001"
    assert fields["packer"].value == "XYZ Packaging Ltd"
    assert fields["importer"].value == "Example Imports Pvt Ltd"
    assert fields["mrp"].value == "₹100"
    assert fields["net_quantity"].value == "500 g"
    assert fields["manufacturing_date"].value == "08/2026"
    assert fields["packing_date"].value == "15/08/2026"
    assert fields["best_before"].value == "6 months"
    assert fields["use_by"].value == "08/2027"
    assert fields["expiry_date"].value == "12/2027"
    assert fields["consumer_care_phone"].value == "1800-123-4567"
    assert fields["consumer_care_email"].value == "care@example.com"
    assert fields["consumer_care_website"].value == "www.example.com"

@pytest.mark.parametrize(("text", "field", "expected"), [
    ("एमआरपी ₹100\nशुद्ध मात्रा: 500 ग्राम", "mrp", "₹100"),
    ("निर्माता: ABC Foods\nनिर्माण तिथि: 08/2026", "manufacturer", "ABC Foods"),
    ("Net Qty 1kg", "net_quantity", "1 kg"),
    ("Contents: 250 ml", "net_quantity", "250 ml"),
    ("M F G: 08/2026\nMRP Rs.l00", "mrp", None),
])
def test_supported_english_hindi_and_noise_patterns(service: ExtractionService, text: str, field: str, expected: str | None) -> None:
    assert service.extract(text)[field].value == expected


def test_multiple_candidates_require_review(service: ExtractionService) -> None:
    fields = service.extract("MRP ₹100\nMRP ₹120\nNet Qty: 500g\nNet Qty: 1kg\nManufacturer: ABC Foods\nManufacturer: XYZ Foods")
    assert fields["mrp"].value == "₹100" and fields["mrp"].needs_review
    assert fields["net_quantity"].value == "500 g" and fields["net_quantity"].needs_review
    assert fields["manufacturer"].value == "ABC Foods" and fields["manufacturer"].needs_review


def test_no_fabrication_and_month_year_precision(service: ExtractionService) -> None:
    fields = service.extract("ABC Foods\n08/2026\n₹100\nBest Before 18 months from manufacture")
    assert fields["manufacturer"].value is None
    assert fields["mrp"].value is None
    assert fields["expiry_date"].value is None
    assert fields["best_before"].value == "18 months from manufacture"
    assert fields["best_before"].value != "01/08/2026"


@pytest.mark.parametrize("text", ["", "Random artwork\nBatch 42\nBlue packaging"])
def test_empty_and_unrelated_ocr_produces_only_conservative_results(service: ExtractionService, text: str) -> None:
    fields = service.extract(text)
    assert fields["manufacturer"].value is None
    assert fields["mrp"].value is None
    for field in fields.values():
        assert 0.0 <= field.confidence <= 1.0
        assert isinstance(field.needs_review, bool)
