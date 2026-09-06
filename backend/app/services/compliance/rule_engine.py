"""Deterministic, explainable checks over Milestone 6 extraction evidence."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import re


LOW_CONFIDENCE = 0.75
VALID_QUANTITY_UNITS = frozenset({"mg", "g", "kg", "ml", "cl", "l"})


@dataclass(frozen=True)
class FieldEvidence:
    value: str | None = None
    confidence: float | None = None
    needs_review: bool = False
    evidence: str | None = None


@dataclass(frozen=True)
class ComplianceFinding:
    rule_id: str
    rule_name: str
    status: str
    severity: str
    message: str
    field: str | None = None
    value: str | None = None
    confidence: float | None = None
    evidence: str | None = None


RULES = (
    ("PRODUCT_IDENTITY", "Product identity", "product_name", "WARNING"),
    ("MANUFACTURER_INFORMATION", "Manufacturer information", "manufacturer", "INFO"),
    ("PACKER_INFORMATION", "Packer information", "packer", "INFO"),
    ("IMPORTER_INFORMATION", "Importer information", "importer", "INFO"),
    ("MRP_FORMAT", "MRP format", "mrp", "WARNING"),
    ("NET_QUANTITY_FORMAT", "Net quantity format", "net_quantity", "WARNING"),
    ("DATE_CONSISTENCY", "Date consistency", "dates", "WARNING"),
    ("CONSUMER_CARE_FORMAT", "Consumer-care format", "consumer_care", "INFO"),
)


class ComplianceEngine:
    """Pure rule engine: equal persisted extraction input produces equal output."""

    def evaluate(self, fields: dict[str, FieldEvidence]) -> list[ComplianceFinding]:
        findings = [self._identity(fields), self._role(fields, "manufacturer"), self._role(fields, "packer"), self._role(fields, "importer"), self._mrp(fields), self._quantity(fields), self._dates(fields), self._consumer_care(fields)]
        findings.extend(self._uncertainty_findings(fields))
        return findings

    @staticmethod
    def _finding(rule_id: str, rule_name: str, status: str, severity: str, message: str, field: str | None = None, item: FieldEvidence | None = None) -> ComplianceFinding:
        return ComplianceFinding(rule_id, rule_name, status, severity, message, field, item.value if item else None, item.confidence if item else None, item.evidence if item else None)

    def _identity(self, fields: dict[str, FieldEvidence]) -> ComplianceFinding:
        item = fields.get("product_name", FieldEvidence())
        if not item.value:
            return self._finding("PRODUCT_IDENTITY", "Product identity", "REVIEW", "WARNING", "No product identity was extracted; manual review is required.", "product_name", item)
        return self._finding("PRODUCT_IDENTITY", "Product identity", "PASS", "WARNING", "A product identity was extracted.", "product_name", item)

    def _role(self, fields: dict[str, FieldEvidence], field: str) -> ComplianceFinding:
        item = fields.get(field, FieldEvidence())
        name = field.capitalize() + " information"
        if not item.value:
            return self._finding(f"{field.upper()}_INFORMATION", name, "REVIEW", "INFO", f"No {field} value was extracted; applicability is not configured and requires review.", field, item)
        if not item.value.strip():
            return self._finding(f"{field.upper()}_INFORMATION", name, "FAIL", "INFO", f"The extracted {field} value is empty.", field, item)
        return self._finding(f"{field.upper()}_INFORMATION", name, "PASS", "INFO", f"A non-empty {field} value was extracted.", field, item)

    def _mrp(self, fields: dict[str, FieldEvidence]) -> ComplianceFinding:
        item = fields.get("mrp", FieldEvidence())
        if not item.value:
            return self._finding("MRP_FORMAT", "MRP format", "REVIEW", "WARNING", "No MRP was extracted; any requirement for it must be configured and reviewed.", "mrp", item)
        match = re.fullmatch(r"\s*(?:₹|rs\.?|inr)\s*([0-9]+(?:[,.][0-9]{1,2})?)\s*", item.value, re.I)
        if not match or float(match.group(1).replace(",", "")) <= 0:
            return self._finding("MRP_FORMAT", "MRP format", "FAIL", "WARNING", "The extracted MRP does not have a positive recognized monetary representation.", "mrp", item)
        return self._finding("MRP_FORMAT", "MRP format", "PASS", "WARNING", "The extracted MRP has a recognized positive monetary representation.", "mrp", item)

    def _quantity(self, fields: dict[str, FieldEvidence]) -> ComplianceFinding:
        item = fields.get("net_quantity", FieldEvidence())
        if not item.value:
            return self._finding("NET_QUANTITY_FORMAT", "Net quantity format", "REVIEW", "WARNING", "No net quantity was extracted; applicability requires review.", "net_quantity", item)
        match = re.fullmatch(r"\s*([0-9]+(?:[.,][0-9]+)?)\s*([a-zA-Z]+)\s*", item.value)
        if not match or float(match.group(1).replace(",", ".")) <= 0 or match.group(2).lower() not in VALID_QUANTITY_UNITS:
            return self._finding("NET_QUANTITY_FORMAT", "Net quantity format", "FAIL", "WARNING", "The extracted net quantity is not a positive value with a recognized unit.", "net_quantity", item)
        return self._finding("NET_QUANTITY_FORMAT", "Net quantity format", "PASS", "WARNING", "The extracted net quantity has a positive recognized unit.", "net_quantity", item)

    @staticmethod
    def _parse_date(value: str) -> date | None:
        value = value.strip()
        month_year = re.fullmatch(r"(\d{1,2})[/.\-](\d{4})", value)
        full = re.fullmatch(r"(\d{1,2})[/.\-](\d{1,2})[/.\-](\d{2,4})", value)
        try:
            if month_year:
                return date(int(month_year.group(2)), int(month_year.group(1)), 1)
            if full:
                year = int(full.group(3)); year += 2000 if year < 100 else 0
                return date(year, int(full.group(2)), int(full.group(1)))
        except ValueError:
            return None
        return None

    def _dates(self, fields: dict[str, FieldEvidence]) -> ComplianceFinding:
        starts = [(name, self._parse_date(item.value)) for name in ("manufacturing_date", "packing_date") if (item := fields.get(name, FieldEvidence())).value]
        ends = [(name, self._parse_date(item.value)) for name in ("expiry_date", "use_by") if (item := fields.get(name, FieldEvidence())).value]
        supplied = [(name, fields[name]) for name in ("manufacturing_date", "packing_date", "expiry_date", "use_by") if name in fields and fields[name].value]
        invalid = [name for name, item in supplied if self._parse_date(item.value or "") is None]
        if invalid:
            return self._finding("DATE_CONSISTENCY", "Date consistency", "REVIEW", "WARNING", f"The date value for {', '.join(invalid)} is ambiguous or cannot be compared.", invalid[0], fields[invalid[0]])
        for start_name, start in starts:
            for end_name, end in ends:
                if start and end and start > end:
                    return self._finding("DATE_CONSISTENCY", "Date consistency", "FAIL", "WARNING", f"{start_name} is later than {end_name}.", start_name, fields[start_name])
        return self._finding("DATE_CONSISTENCY", "Date consistency", "PASS", "WARNING", "Available comparable date values are internally consistent.")

    def _consumer_care(self, fields: dict[str, FieldEvidence]) -> ComplianceFinding:
        validators = {
            "consumer_care_email": lambda value: bool(re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", value)),
            "consumer_care_phone": lambda value: 10 <= len(re.sub(r"\D", "", value)) <= 13,
            "consumer_care_website": lambda value: bool(re.fullmatch(r"(?:https?://)?(?:www\.)?[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+/?", value)),
        }
        seen = False
        for field, valid in validators.items():
            item = fields.get(field, FieldEvidence())
            if item.value:
                seen = True
                if not valid(item.value):
                    return self._finding("CONSUMER_CARE_FORMAT", "Consumer-care format", "REVIEW", "INFO", f"The extracted {field.replace('_', ' ')} has an unrecognized structure.", field, item)
        message = "Available consumer-care information has a recognizable basic structure." if seen else "No consumer-care information was extracted; no requirement is assumed."
        return self._finding("CONSUMER_CARE_FORMAT", "Consumer-care format", "PASS", "INFO", message)

    def _uncertainty_findings(self, fields: dict[str, FieldEvidence]) -> list[ComplianceFinding]:
        findings = []
        for field, item in fields.items():
            if item.value and (item.needs_review or (item.confidence is not None and item.confidence < LOW_CONFIDENCE)):
                findings.append(self._finding("LOW_CONFIDENCE_" + field.upper(), "Extraction confidence review", "REVIEW", "WARNING", "The extracted value requires manual verification before it is treated as authoritative.", field, item))
        return findings
