"""Deterministic, evidence-only risk scoring for completed inspections."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.models import ComplianceResult, ComplianceRule, ExtractedField, Inspection, Product

# Central policy constants.  These are prioritisation weights, not legal rules.
RISK_LEVELS = ((75, "CRITICAL"), (50, "HIGH"), (25, "MEDIUM"), (0, "LOW"))
FAILURE_POINTS = {"HIGH": 35, "WARNING": 25, "MEDIUM": 25, "INFO": 15, "LOW": 10}
REVIEW_POINTS = {"HIGH": 20, "WARNING": 12, "MEDIUM": 12, "INFO": 6, "LOW": 4}
MISSING_FIELD_POINTS = 6
MISSING_FIELD_CAP = 18
REPEATED_RULE_POINTS = 12
REPEATED_FIELD_POINTS = 8
MULTIPLE_FINDINGS_POINTS = 8
MULTIPLE_FINDINGS_MINIMUM = 3


@dataclass(frozen=True)
class RiskReason:
    type: str
    points: int
    description: str
    rule_code: str | None = None
    severity: str | None = None
    field: str | None = None
    occurrences: int | None = None


@dataclass(frozen=True)
class RiskAssessment:
    risk_score: int
    risk_level: str
    reasons: list[RiskReason]


def risk_level(score: int) -> str:
    return next(level for threshold, level in RISK_LEVELS if score >= threshold)


class RiskService:
    """Scores only persisted compliance/extraction evidence; it never reads OCR."""
    def __init__(self, db: Session, minimum_occurrences: int = 2):
        self.db, self.minimum_occurrences = db, minimum_occurrences

    def _evidence(self, inspections: list[Inspection]):
        ids = [inspection.id for inspection in inspections]
        if not ids:
            return {}, {}, {}
        results = self.db.execute(
            select(ComplianceResult.inspection_id, ComplianceResult, ComplianceRule)
            .join(ComplianceRule, ComplianceRule.id == ComplianceResult.rule_id)
            .where(ComplianceResult.inspection_id.in_(ids))
        ).all()
        fields = self.db.execute(
            select(ExtractedField.inspection_id, ExtractedField)
            .where(ExtractedField.inspection_id.in_(ids), ExtractedField.value.is_(None))
        ).all()
        by_inspection: dict[UUID, list[tuple[ComplianceResult, ComplianceRule]]] = defaultdict(list)
        rule_counts: dict[str, int] = defaultdict(int)
        for inspection_id, result, rule in results:
            by_inspection[inspection_id].append((result, rule))
            if result.result in ("FAIL", "REVIEW"):
                rule_counts[rule.rule_code] += 1
        missing: dict[UUID, set[str]] = defaultdict(set)
        field_counts: dict[str, int] = defaultdict(int)
        for inspection_id, field in fields:
            missing[inspection_id].add(field.field_name)
        for names in missing.values():
            for name in names:
                field_counts[name] += 1
        return by_inspection, missing, {"rules": rule_counts, "fields": field_counts}

    def assess(self, inspection: Inspection, results: list[tuple[ComplianceResult, ComplianceRule]], missing_fields: set[str], counts: dict) -> RiskAssessment:
        reasons: list[RiskReason] = []
        non_pass = []
        for result, rule in sorted(results, key=lambda item: item[1].rule_code):
            if result.result not in ("FAIL", "REVIEW"):
                continue
            non_pass.append((result, rule))
            points = (FAILURE_POINTS if result.result == "FAIL" else REVIEW_POINTS).get(rule.severity, REVIEW_POINTS["INFO"])
            kind = "COMPLIANCE_FAILURE" if result.result == "FAIL" else "COMPLIANCE_WARNING"
            reasons.append(RiskReason(kind, points, result.explanation, rule.rule_code, rule.severity, result.field_name))
        # Missing extraction values are explanatory only; no legal requirement is inferred.
        for field in sorted(missing_fields)[: MISSING_FIELD_CAP // MISSING_FIELD_POINTS]:
            reasons.append(RiskReason("MISSING_FIELD", MISSING_FIELD_POINTS, f"{field.replace('_', ' ').capitalize()} was not extracted and requires review.", field=field))
        seen_rules = set()
        for _, rule in non_pass:
            if rule.rule_code not in seen_rules and counts["rules"][rule.rule_code] >= self.minimum_occurrences:
                seen_rules.add(rule.rule_code)
                reasons.append(RiskReason("REPEATED_PATTERN", REPEATED_RULE_POINTS, "Same compliance issue has appeared repeatedly in completed inspections.", rule.rule_code, rule.severity, occurrences=counts["rules"][rule.rule_code]))
        for field in sorted(missing_fields):
            if counts["fields"][field] >= self.minimum_occurrences:
                reasons.append(RiskReason("REPEATED_PATTERN", REPEATED_FIELD_POINTS, "Missing extracted field has appeared repeatedly in completed inspections.", field=field, occurrences=counts["fields"][field]))
        if len({rule.rule_code for _, rule in non_pass}) >= MULTIPLE_FINDINGS_MINIMUM:
            reasons.append(RiskReason("MULTIPLE_FINDINGS", MULTIPLE_FINDINGS_POINTS, "Multiple distinct compliance findings require combined attention."))
        score = min(100, max(0, sum(reason.points for reason in reasons)))
        return RiskAssessment(score, risk_level(score), reasons)

    def for_user(self, user_id: UUID) -> list[tuple[Inspection, str | None, RiskAssessment, str]]:
        rows = self.db.execute(
            select(Inspection, Product.name).outerjoin(Product, Product.id == Inspection.product_id)
            .where(Inspection.user_id == user_id, Inspection.status == "COMPLETED")
        ).all()
        inspections = [inspection for inspection, _ in rows]
        results, missing, counts = self._evidence(inspections)
        output = []
        for inspection, product_name in rows:
            assessment = self.assess(inspection, results.get(inspection.id, []), missing.get(inspection.id, set()), counts)
            statuses = [result.result for result, _ in results.get(inspection.id, [])]
            compliance_status = "FAIL" if "FAIL" in statuses else "WARNING" if "REVIEW" in statuses else "PASS"
            output.append((inspection, product_name, assessment, compliance_status))
        return sorted(output, key=lambda row: (-row[2].risk_score, -(3 if row[2].risk_level == "CRITICAL" else 2 if row[2].risk_level == "HIGH" else 1 if row[2].risk_level == "MEDIUM" else 0), -(row[0].completed_at or row[0].created_at).timestamp(), str(row[0].id)))

    def for_inspection(self, inspection: Inspection) -> RiskAssessment:
        # Repeat context is intentionally limited to the inspection owner's completed history.
        items = self.for_user(inspection.user_id) if inspection.user_id else []
        for candidate, _, assessment, _ in items:
            if candidate.id == inspection.id:
                return assessment
        return RiskAssessment(0, "LOW", [])
