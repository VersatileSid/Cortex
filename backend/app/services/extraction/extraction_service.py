"""Deterministic, evidence-preserving package-label extraction heuristics."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from backend.app.services.compliance.rule_engine import ComplianceEngine

logger = logging.getLogger(__name__)


FIELD_NAMES = (
    "product_name", "manufacturer", "packer", "importer", "manufacturer_address",
    "packer_address", "importer_address", "mrp", "net_quantity", "manufacturing_date",
    "packing_date", "best_before", "use_by", "expiry_date", "consumer_care_phone",
    "consumer_care_email", "consumer_care_website",
)


@dataclass(frozen=True)
class ExtractedValue:
    value: str | None = None
    confidence: float = 0.0
    needs_review: bool = False
    source_text: str | None = None
    matched_pattern: str | None = None
    normalized_value: str | None = None


class ExtractionService:
    """Rule-based extraction; confidence is a heuristic, never a probability."""

    _date = r"(?:\d{1,2}[/.\-]\d{1,2}[/.\-]\d{2,4}|\d{1,2}[/.\-]\d{4})"
    _money = r"(?:₹|rs\.?|inr)\s*([0-9][0-9,.]*)"
    _quantity = r"([0-9OoIl]+(?:[.,][0-9OoIl]+)?)\s*(m\s*l|mgs?|milligrams?|g(?:rams?)?|gms?|k(?:ilo)?grams?|kgs?|millilit(?:re|er)s?|ml|centilit(?:re|er)s?|cl|l(?:it(?:re|er)s?)?|ltr)\b"
    _roles = {
        "manufacturer": r"(?:manufacturer|manufactured?\s*(?:by)?|mfg\.?\s*by|mfd\.?\s*by|निर्माता|निर्मित\s*द्वारा)",
        "packer": r"(?:packed?\s*(?:by|for)?|pkd\.?\s*by|packer|पैक\s*किया\s*गया|पैकर)",
        "importer": r"(?:imported?\s*by|importer|आयातक)",
    }

    def extract(self, ocr_text: str) -> dict[str, ExtractedValue]:
        lines = [self._clean(line) for line in ocr_text.splitlines() if self._clean(line)]
        results = {name: ExtractedValue() for name in FIELD_NAMES}
        if not lines:
            return results
        results.update(self._entities(lines))
        results["mrp"] = self._single_candidate(lines, self._mrp_candidates(lines), "MRP")
        results["net_quantity"] = self._single_candidate(lines, self._quantity_candidates(lines), "quantity")
        results.update(self._dates(lines))
        results.update(self._consumer_care(lines))
        results["product_name"] = self._product_name(lines, results)
        return results

    @staticmethod
    def _clean(value: str) -> str:
        return re.sub(r"\s+", " ", value).strip(" :-|\t")

    def _entities(self, lines: list[str]) -> dict[str, ExtractedValue]:
        values = {name: ExtractedValue() for name in ("manufacturer", "packer", "importer", "manufacturer_address", "packer_address", "importer_address")}
        for role, label in self._roles.items():
            candidates: list[tuple[str, str, str | None]] = []
            for index, line in enumerate(lines):
                match = re.search(rf"(?i)^\s*({label})\s*[:\-]?\s*(.*)$", line)
                if not match:
                    continue
                value = self._clean(match.group(2)) or (lines[index + 1] if index + 1 < len(lines) else "")
                if value and not self._looks_like_metadata(value):
                    address = self._address_after(lines, index, value)
                    candidates.append((value, line, address))
            if candidates:
                unique = list(dict.fromkeys(item[0] for item in candidates))
                chosen_value, source, address = candidates[0]
                ambiguous = len(unique) > 1
                values[role] = ExtractedValue(chosen_value, 0.70 if ambiguous else 0.94, ambiguous, source, "explicit_role_label", chosen_value)
                if address:
                    values[f"{role}_address"] = ExtractedValue(address, 0.82 if not ambiguous else 0.62, ambiguous, source, "lines_after_explicit_role", address)
        return values

    def _address_after(self, lines: list[str], label_index: int, entity_value: str) -> str | None:
        start = label_index + (1 if not re.search(r"(?i)(?:by|manufacturer|packer|importer)\s*[:\-]?\s*$", lines[label_index]) else 2)
        parts: list[str] = []
        for line in lines[start:start + 3]:
            if self._is_context_line(line) or re.search(r"@|https?://|www\.|\b(?:mrp|net qty|mfg|packed|exp)\b", line, re.I):
                break
            if re.search(r"\d|area|road|street|nagar|delhi|pincode|pin\b|भारत|नगर", line, re.I):
                parts.append(line)
            elif parts:
                parts.append(line)
        return ", ".join(parts) or None

    @staticmethod
    def _looks_like_metadata(value: str) -> bool:
        return bool(re.search(r"(?:₹|\b(?:rs|inr|mg|kg|ml|mfg|exp)\b|@)", value, re.I))

    def _is_context_line(self, line: str) -> bool:
        return any(re.search(pattern, line, re.I) for pattern in self._roles.values())

    def _mrp_candidates(self, lines: list[str]) -> list[tuple[str, str, float]]:
        candidates = []
        for line in lines:
            explicit = re.search(rf"(?i)(?:m\s*r\s*p|maximum\s+retail\s+price|एमआरपी|अधिकतम\s+खुदरा\s+मूल्य)\s*[:\-]?\s*{self._money}", line)
            if explicit:
                candidates.append((f"₹{explicit.group(1).replace(',', '')}", line, 0.97))
        return candidates

    def _quantity_candidates(self, lines: list[str]) -> list[tuple[str, str, float]]:
        candidates = []
        for line in lines:
            match = re.search(rf"(?i)(?:net\s*(?:quantity|qty|weight)|contents|शुद्ध\s*मात्रा)\s*[:\-]?\s*{self._quantity}", line)
            if match:
                normalized = ComplianceEngine.normalize_quantity(f"{match.group(1)} {match.group(2)}")
                if normalized:
                    logger.debug("Extraction field=net_quantity raw_ocr=%r parsed=%r normalized=%r", line, f"{match.group(1)} {match.group(2)}", normalized)
                    candidates.append((normalized, line, 0.96))
        return candidates

    def _dates(self, lines: list[str]) -> dict[str, ExtractedValue]:
        patterns = {
            "manufacturing_date": r"(?:mfg\.?|mfd\.?|manufactured?(?:\s+on|\s+date)?|manufacturing\s+date|निर्माण\s*तिथि)",
            "packing_date": r"(?:packed?\s*(?:on|date)?|pkd\.?|packing\s+date|पैकिंग\s*तिथि)",
            "use_by": r"(?:use\s+by|उपयोग\s*करने\s*की\s*अंतिम\s*तिथि)",
            "expiry_date": r"(?:expiry(?:\s+date)?|exp\.?|समाप्ति)",
            "best_before": r"(?:best\s+before(?:\s+date)?|बेस्ट\s*बिफोर)",
        }
        result = {name: ExtractedValue() for name in patterns}
        for field, label in patterns.items():
            found: list[tuple[str, str]] = []
            for line in lines:
                match = re.search(rf"(?i){label}\s*[:\-]?\s*({self._date}|\d+\s+months?(?:\s+from\s+manufacture)?)", line)
                if match:
                    found.append((match.group(1).lower() if "month" in match.group(1).lower() else match.group(1), line))
            result[field] = self._single_candidate(lines, [(value, source, 0.94) for value, source in found], field)
        return result

    def _consumer_care(self, lines: list[str]) -> dict[str, ExtractedValue]:
        result = {name: ExtractedValue() for name in ("consumer_care_phone", "consumer_care_email", "consumer_care_website")}
        context = r"(?:customer\s*care|consumer\s*care|helpline|contact|toll\s*free|call|ग्राहक\s*सेवा|उपभोक्ता\s*सेवा)"
        for line in lines:
            if re.search(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+", line):
                value = re.search(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+", line).group(0)
                result["consumer_care_email"] = ExtractedValue(value, 0.96, False, line, "email", value)
            website = re.search(r"(?i)(?:https?://)?(?:www\.)?[a-z0-9-]+(?:\.[a-z0-9-]+)+", line)
            if website and "@" not in line:
                value = website.group(0)
                result["consumer_care_website"] = ExtractedValue(value, 0.91, False, line, "website", value)
            if re.search(context, line, re.I):
                phone = re.search(r"(?<!\d)(?:\+?91[\s-]?)?(?:\d[\s-]?){10,12}\d(?!\d)", line)
                if phone:
                    value = re.sub(r"\s+", " ", phone.group(0)).strip()
                    result["consumer_care_phone"] = ExtractedValue(value, 0.92, False, line, "consumer_care_phone", value)
        return result

    def _product_name(self, lines: list[str], results: dict[str, ExtractedValue]) -> ExtractedValue:
        blocked = {value.value for key, value in results.items() if key in self._roles and value.value}
        for line in lines[:4]:
            if line not in blocked and not self._looks_like_metadata(line) and not self._is_context_line(line) and len(line) <= 80 and re.search(r"[A-Za-z\u0900-\u097F]", line):
                return ExtractedValue(line, 0.48, True, line, "early_non_metadata_line", line)
        return ExtractedValue()

    @staticmethod
    def _single_candidate(lines: list[str], candidates: list[tuple[str, str, float]], pattern: str) -> ExtractedValue:
        if not candidates:
            return ExtractedValue()
        values = list(dict.fromkeys(candidate[0] for candidate in candidates))
        value, source, confidence = candidates[0]
        ambiguous = len(values) > 1
        return ExtractedValue(value, confidence - (0.25 if ambiguous else 0), ambiguous, source, pattern, value)
