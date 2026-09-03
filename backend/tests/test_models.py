from backend.app.models import Base


def test_required_tables_are_registered() -> None:
    expected_tables = {
        "users", "manufacturers", "products", "inspections", "inspection_images",
        "ocr_results", "extracted_fields", "compliance_rules", "compliance_results",
        "inspection_issues", "risk_scores", "manufacturer_history", "sync_records",
    }

    assert expected_tables <= set(Base.metadata.tables)


def test_inspection_number_and_sync_id_are_unique() -> None:
    inspections = Base.metadata.tables["inspections"]
    sync_records = Base.metadata.tables["sync_records"]

    assert inspections.c.inspection_number.unique is True
    assert sync_records.c.client_sync_id.unique is True
