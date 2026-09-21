"""Fail closed when a citation is not a verbatim approved span."""

from __future__ import annotations

import re

from src.models import Claim, Recommendation

_PERCENT = re.compile(r"\d+(?:\.\d+)?%")
_DOSE = re.compile(r"\d+(?:\.\d+)?\s*mg", re.IGNORECASE)


def claim_is_grounded(claim: Claim, sources: dict[str, str]) -> bool:
    """True when the excerpt is quoted from the cited source and used in the statement."""
    blob = sources.get(claim.source_id, "")
    excerpt = claim.excerpt.strip()
    if len(excerpt) < 12 or excerpt not in blob or excerpt not in claim.statement:
        return False
    if claim.source_id not in sources:
        return False
    for percent in _PERCENT.findall(claim.statement):
        if percent not in excerpt:
            return False
    compact_excerpt = _compact(excerpt)
    for dose in _DOSE.findall(claim.statement):
        if _compact(dose) not in compact_excerpt:
            return False
    return True


def enforce_grounding(
    recommendations: list[Recommendation],
    sources: dict[str, str],
) -> list[Recommendation]:
    """Withhold any recommendation that cites a span the corpus does not contain."""
    checked: list[Recommendation] = []
    for rec in recommendations:
        bad = [claim.source_id for claim in rec.claims if not claim_is_grounded(claim, sources)]
        if bad:
            rec.withheld = True
            rec.withhold_reason = "Ungrounded citation withheld: " + ", ".join(bad)
            rec.hitl = True
            if "grounding_failure" not in rec.hitl_reasons:
                rec.hitl_reasons.append("grounding_failure")
        elif _efficacy_without_fair_balance(rec):
            rec.withheld = True
            rec.withhold_reason = "Efficacy statement withheld because fair balance was not attached."
            rec.hitl = True
            if "fair_balance_missing" not in rec.hitl_reasons:
                rec.hitl_reasons.append("fair_balance_missing")
        checked.append(rec)
    return checked


def _efficacy_without_fair_balance(rec: Recommendation) -> bool:
    cites_efficacy = any(claim.source_id == "CNT-EFF-001" for claim in rec.claims)
    cites_balance = any(claim.source_id == "CNT-FB-001" for claim in rec.claims)
    return cites_efficacy and not cites_balance


def _compact(text: str) -> str:
    return re.sub(r"\s+", "", text).lower()
