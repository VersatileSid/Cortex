"""Structured, declared-quantity evidence for the existing compliance pipeline.

This service does not make a legal decision and never claims a physical
measurement.  It only presents the label declaration already extracted and
the authoritative result of the existing quantity compliance rule.
"""
from __future__ import annotations

from dataclasses import dataclass

from backend.app.services.compliance.rule_engine import ComplianceEngine


@dataclass(frozen=True)
class QuantityVerification:
    declared_quantity: str | None
    normalized_quantity: str | None
    unit: str | None
    status: str
    reason: str
    rule_code: str = "NET_QUANTITY_FORMAT"
    severity: str = "WARNING"
    evidence: str | None = None
    requirement: str | None = None


class QuantityVerificationService:
    """Adapts extraction evidence to the stable quantity compliance finding."""

    @staticmethod
    def _unit(normalized: str | None) -> str | None:
        return normalized.rsplit(" ", 1)[1] if normalized and " " in normalized else None

    def verify(
        self,
        declared_quantity: str | None,
        *,
        status: str | None = None,
        reason: str | None = None,
        severity: str | None = None,
        evidence: str | None = None,
        requirement: str | None = None,
    ) -> QuantityVerification:
        normalized = ComplianceEngine.normalize_quantity(declared_quantity)
        # Compliance remains authoritative when it has run.  Before then, use
        # REVIEW rather than presenting an unvalidated declaration as PASS.
        resolved_status = status or "REVIEW"
        if reason is None:
            reason = (
                "A declared quantity was extracted and awaits compliance evaluation."
                if declared_quantity else "No reliable declared quantity was extracted."
            )
        return QuantityVerification(
            declared_quantity=declared_quantity,
            normalized_quantity=normalized,
            unit=self._unit(normalized),
            status=resolved_status,
            reason=reason,
            severity=severity or "WARNING",
            evidence=evidence or declared_quantity,
            requirement=requirement,
        )
