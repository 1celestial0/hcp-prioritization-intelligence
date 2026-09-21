"""Score fictional HCPs for one approved indication."""

from __future__ import annotations

from datetime import date

from src.config import (
    APPROVED_SPECIALTIES,
    AS_OF,
    CONTENT_BONUS,
    ENGAGEMENT_CAP,
    ENGAGEMENT_WINDOW_DAYS,
    HITL_CONFIDENCE_THRESHOLD,
    LIMITED_SPECIALTIES,
    OUTCOME_POINTS,
    POSITIVE_CONTENT_OUTCOMES,
    TIER_POINTS,
)
from src.models import Catalog, Claim, Recommendation, RetrievalResult

PARTIAL_FIT_MAX = 22


def rank_hcps(
    catalog: Catalog,
    retrieval: RetrievalResult,
    *,
    as_of: date = AS_OF,
) -> list[Recommendation]:
    """Rank every roster HCP. Outside-audience scores stay at zero."""
    if not retrieval.ok:
        return []

    retrieved_ids = set(retrieval.content_ids)
    on_indication_ids = {
        doc.content_id
        for doc in catalog.documents
        if retrieval.indication in doc.indication_tags
    }
    recommendations: list[Recommendation] = []
    for hcp in catalog.hcps:
        history = catalog.interactions_by_hcp.get(hcp.hcp_id, [])
        recommendations.append(
            _score_hcp(
                catalog,
                hcp_id=hcp.hcp_id,
                history=history,
                retrieved_ids=retrieved_ids,
                on_indication_ids=on_indication_ids,
                as_of=as_of,
            )
        )

    recommendations.sort(key=lambda rec: (-rec.score, -rec.confidence, rec.hcp_id))
    for index, rec in enumerate(recommendations, start=1):
        rec.rank = index
    return recommendations


def _score_hcp(
    catalog: Catalog,
    *,
    hcp_id: str,
    history: list,
    retrieved_ids: set[str],
    on_indication_ids: set[str],
    as_of: date,
) -> Recommendation:
    hcp = catalog.hcp_by_id[hcp_id]
    pediatric = _is_pediatric(hcp.specialty, hcp.panel_focus)
    fit = _audience_fit(hcp.specialty, pediatric)
    recent = [
        row
        for row in history
        if 0 <= (as_of - row.interaction_date).days <= ENGAGEMENT_WINDOW_DAYS
    ]
    engagement = _engagement(recent, on_indication_ids)
    conflict = {"declined", "requested_info"}.issubset({row.outcome for row in recent})
    whitespace = _whitespace(fit, history, as_of)
    tier_points = TIER_POINTS[hcp.tier]

    if fit == 0:
        components = {"audience_fit": 0, "engagement": 0, "tier": 0, "whitespace": 0}
    else:
        components = {
            "audience_fit": fit,
            "engagement": engagement,
            "tier": tier_points,
            "whitespace": whitespace,
        }
    score = sum(components.values())
    confidence = _confidence(
        fit=fit,
        recent=recent,
        conflict=conflict,
        pediatric=pediatric,
        as_of=as_of,
    )
    hitl_reasons = _hitl_reasons(
        fit=fit,
        confidence=confidence,
        conflict=conflict,
        pediatric=pediatric,
        recent_count=len(recent),
    )

    claims: list[Claim] = [
        _quote(
            "Roster",
            f"specialty {hcp.specialty} tier {hcp.tier} territory {hcp.territory_id}",
            "roster",
            hcp.hcp_id,
        ),
        _quote("Audience rule", catalog.audience_rule.text(), "rule", catalog.audience_rule.rule_id),
    ]
    for row in recent[:3] or history[:1]:
        claims.append(_quote("Interaction", row.text(), "interaction", row.interaction_id))

    claims.extend(
        _talking_points(
            catalog,
            fit=fit,
            pediatric=pediatric,
            conflict=conflict,
            panel_focus=hcp.panel_focus,
            retrieved_ids=retrieved_ids,
            hitl_reasons=hitl_reasons,
        )
    )

    return Recommendation(
        hcp_id=hcp.hcp_id,
        display_name=hcp.display_name,
        specialty=hcp.specialty,
        tier=hcp.tier,
        territory_id=hcp.territory_id,
        rank=0,
        score=score,
        confidence=confidence,
        hitl=bool(hitl_reasons),
        hitl_reasons=hitl_reasons,
        claims=claims,
        components=components,
    )


def _audience_fit(specialty: str, pediatric: bool) -> int:
    if pediatric:
        return 0
    normalized = specialty.strip().lower()
    if normalized in APPROVED_SPECIALTIES:
        return 35
    if normalized in LIMITED_SPECIALTIES:
        return 12
    return 0


def _is_pediatric(specialty: str, panel_focus: str) -> bool:
    return "pediatric" in specialty.lower() or panel_focus == "pediatric_unapproved"


def _engagement(recent: list, on_indication_ids: set[str]) -> int:
    raw = 0
    for row in recent:
        raw += OUTCOME_POINTS[row.outcome]
        if row.outcome in POSITIVE_CONTENT_OUTCOMES and row.content_id in on_indication_ids:
            raw += CONTENT_BONUS
    return max(0, min(ENGAGEMENT_CAP, raw))


def _whitespace(fit: int, history: list, as_of: date) -> int:
    if fit < PARTIAL_FIT_MAX:
        return 0
    if not history:
        return 15
    last = max(history, key=lambda row: row.interaction_date)
    days = (as_of - last.interaction_date).days
    if days >= 120:
        return 15
    if days >= 60:
        return 8
    return 0


def _confidence(*, fit: int, recent: list, conflict: bool, pediatric: bool, as_of: date) -> float:
    if pediatric:
        return 0.40
    if fit == 0:
        return 0.90
    score = 0.45
    score += 0.25 if fit >= 35 else 0.08
    if len(recent) >= 2:
        score += 0.15
    elif len(recent) == 1:
        score += 0.08
    score += 0.10  # retrieval already succeeded
    if conflict:
        score -= 0.25
    if len(recent) == 0:
        score -= 0.20
    elif (
        len(recent) == 1
        and recent[0].outcome == "no_response"
        and (as_of - recent[0].interaction_date).days > 90
    ):
        score -= 0.15
    return round(max(0.05, min(0.95, score)), 2)


def _hitl_reasons(
    *,
    fit: int,
    confidence: float,
    conflict: bool,
    pediatric: bool,
    recent_count: int,
) -> list[str]:
    reasons: list[str] = []
    if pediatric:
        reasons.append("safety_sensitive_population")
    if conflict:
        reasons.append("conflicting_engagement")
    if 0 < fit < PARTIAL_FIT_MAX:
        reasons.append("limited_audience_fit")
    if fit >= PARTIAL_FIT_MAX and recent_count == 0:
        reasons.append("no_recent_engagement")
    if confidence < HITL_CONFIDENCE_THRESHOLD:
        reasons.append("confidence_below_threshold")
    return reasons


def _talking_points(
    catalog: Catalog,
    *,
    fit: int,
    pediatric: bool,
    conflict: bool,
    panel_focus: str,
    retrieved_ids: set[str],
    hitl_reasons: list[str],
) -> list[Claim]:
    claims: list[Claim] = []
    efficacy = catalog.allowed_by_id.get("RULE-ALLOW-EFFICACY")
    use_efficacy = (
        efficacy is not None
        and fit >= PARTIAL_FIT_MAX
        and not pediatric
        and not conflict
        and efficacy.content_id in retrieved_ids
        and efficacy.fair_balance_content_id in retrieved_ids
    )
    if use_efficacy and efficacy is not None:
        claims.append(
            _quote(
                "Approved efficacy statement",
                catalog.span(efficacy.content_id, efficacy.span),
                "content",
                efficacy.content_id,
            )
        )
        claims.append(
            _quote(
                "Required fair balance",
                catalog.span(efficacy.fair_balance_content_id or "", efficacy.fair_balance_span or ""),
                "content",
                efficacy.fair_balance_content_id or "",
            )
        )
        return claims

    if efficacy is not None and fit >= PARTIAL_FIT_MAX and not pediatric and not conflict:
        if "fair_balance_unavailable" not in hitl_reasons:
            hitl_reasons.append("fair_balance_unavailable")

    if pediatric and "CNT-DOS-001" in retrieved_ids:
        claims.append(
            _quote(
                "Approved restriction",
                catalog.span("CNT-DOS-001", "no_pediatric_dose"),
                "content",
                "CNT-DOS-001",
            )
        )
    if (pediatric or panel_focus == "dermal_unapproved" or fit == 0) and "CNT-IDN-001" in retrieved_ids:
        claims.append(
            _quote(
                "Approved restriction",
                catalog.span("CNT-IDN-001", "not_pediatric_or_dermal"),
                "content",
                "CNT-IDN-001",
            )
        )
        return claims

    indication = catalog.allowed_by_id.get("RULE-ALLOW-INDICATION")
    if indication is not None and indication.content_id in retrieved_ids:
        claims.append(
            _quote(
                "Approved indication",
                catalog.span(indication.content_id, indication.span),
                "content",
                indication.content_id,
            )
        )
    elif "approved_content_span_missing" not in hitl_reasons:
        hitl_reasons.append("approved_content_span_missing")
    return claims


def _quote(label: str, excerpt: str, source_type: str, source_id: str) -> Claim:
    return Claim(
        statement=f'{label}: "{excerpt}"',
        source_type=source_type,
        source_id=source_id,
        excerpt=excerpt,
    )
