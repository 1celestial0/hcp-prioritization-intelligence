"""Refuse unapproved medical claims. Allowed answers quote the corpus."""

from __future__ import annotations

import re

from src.config import FALLBACK_MESSAGE
from src.models import Catalog, Claim, QueryAnswer
from src.retrieval.retrieve import retrieve_content
from src.safety.grounding import claim_is_grounded

_PERCENT = re.compile(r"\d+(?:\.\d+)?%")
_DOSE = re.compile(r"\d+(?:\.\d+)?\s*mg", re.IGNORECASE)


def answer_query(catalog: Catalog, query: str) -> QueryAnswer:
    """Classify a field question and either refuse it or quote an approved span."""
    prohibited = _matching_prohibited_rule(catalog, query)
    if prohibited is not None:
        return _refusal(catalog, query, prohibited)

    bad_percent = _unapproved_percents(catalog, query)
    if bad_percent:
        rule = catalog.prohibited_by_id.get("RULE-UNAPPROVED-NUMBER")
        if rule is None:
            return _fallback(query, FALLBACK_MESSAGE)
        return _refusal(catalog, query, rule)

    bad_dose = _unapproved_doses(catalog, query)
    if bad_dose:
        rule = catalog.prohibited_by_id.get("RULE-UNAPPROVED-DOSE")
        if rule is None:
            return _fallback(query, FALLBACK_MESSAGE)
        return _refusal(catalog, query, rule)

    return _grounded_answer(catalog, query)


def _matching_prohibited_rule(catalog: Catalog, query: str):
    for rule in catalog.prohibited_rules:
        if any(_contains_phrase(query, pattern) for pattern in rule.patterns):
            return rule
    return None


def _refusal(catalog: Catalog, query: str, rule) -> QueryAnswer:
    claims = [
        Claim(
            statement=f'Refusal rule: "{rule.reason}"',
            source_type="rule",
            source_id=rule.rule_id,
            excerpt=rule.reason,
        )
    ]
    lines = [
        f"REFUSED ({rule.rule_id}): {rule.reason}",
        "No ungrounded medical claim was generated.",
    ]
    if rule.safe_content_id and rule.safe_span:
        excerpt = catalog.span(rule.safe_content_id, rule.safe_span)
        claims.append(
            Claim(
                statement=f'Approved restriction: "{excerpt}"',
                source_type="content",
                source_id=rule.safe_content_id,
                excerpt=excerpt,
            )
        )
        lines.append(f'Approved restriction: "{excerpt}" [{rule.safe_content_id}]')
    rendered = "\n".join(lines)
    sources = catalog.source_index()
    if any(not claim_is_grounded(claim, sources) for claim in claims):
        return _fallback(query, FALLBACK_MESSAGE)
    return QueryAnswer(
        query=query,
        refused=True,
        fallback=False,
        hitl=False,
        rule_id=rule.rule_id,
        reason=rule.reason,
        claims=claims,
        rendered=rendered,
    )


def _grounded_answer(catalog: Catalog, query: str) -> QueryAnswer:
    retrieval = retrieve_content(
        catalog,
        indication=catalog.indication_id,
        query=query,
        top_k=6,
    )
    if not retrieval.ok:
        return _fallback(query, retrieval.fallback_reason or FALLBACK_MESSAGE)

    kind = _question_kind(query)
    rule_id = {
        "fair_balance": "RULE-ALLOW-FAIR-BALANCE",
        "dose": "RULE-ALLOW-DOSE",
        "moa": "RULE-ALLOW-MOA",
        "efficacy": "RULE-ALLOW-EFFICACY",
        "indication": "RULE-ALLOW-INDICATION",
    }[kind]
    rule = catalog.allowed_by_id.get(rule_id)
    if rule is None or rule.content_id not in retrieval.content_ids:
        return _fallback(query, FALLBACK_MESSAGE)

    claims = [
        Claim(
            statement=f'Approved statement: "{catalog.span(rule.content_id, rule.span)}"',
            source_type="content",
            source_id=rule.content_id,
            excerpt=catalog.span(rule.content_id, rule.span),
        )
    ]
    if rule.requires_fair_balance:
        if rule.fair_balance_content_id not in retrieval.content_ids:
            return _fallback(query, "Efficacy answer withheld because fair balance was not retrieved.")
        fb_excerpt = catalog.span(rule.fair_balance_content_id or "", rule.fair_balance_span or "")
        claims.append(
            Claim(
                statement=f'Required fair balance: "{fb_excerpt}"',
                source_type="content",
                source_id=rule.fair_balance_content_id or "",
                excerpt=fb_excerpt,
            )
        )
    if kind == "dose" and "CNT-DOS-001" in retrieval.content_ids:
        restriction = catalog.span("CNT-DOS-001", "no_pediatric_dose")
        if restriction not in claims[0].excerpt:
            claims.append(
                Claim(
                    statement=f'Approved restriction: "{restriction}"',
                    source_type="content",
                    source_id="CNT-DOS-001",
                    excerpt=restriction,
                )
            )

    sources = catalog.source_index()
    if any(not claim_is_grounded(claim, sources) for claim in claims):
        return _fallback(query, FALLBACK_MESSAGE)

    lines = [f"{claim.statement} [{claim.source_id}]" for claim in claims]
    return QueryAnswer(
        query=query,
        refused=False,
        fallback=False,
        hitl=False,
        rule_id=rule.rule_id,
        reason=rule.reason,
        claims=claims,
        rendered="\n".join(lines),
    )


def _fallback(query: str, reason: str) -> QueryAnswer:
    return QueryAnswer(
        query=query,
        refused=False,
        fallback=True,
        hitl=True,
        rule_id=None,
        reason=reason,
        claims=[],
        rendered=f"WITHHELD: {reason}",
        hitl_reason="retrieval_or_grounding_failure",
    )


def _question_kind(query: str) -> str:
    text = query.lower()
    if "fair balance" in text or "fair-balance" in text or "adverse" in text:
        return "fair_balance"
    if "dose" in text or "dosing" in text:
        return "dose"
    if "mechanism" in text or "pathway" in text or "virel-7" in text:
        return "moa"
    if "efficacy" in text or "orion" in text or "symptom-control" in text:
        return "efficacy"
    return "indication"


def _unapproved_percents(catalog: Catalog, query: str) -> list[str]:
    allowed: set[str] = set()
    for document in catalog.documents:
        if catalog.indication_id in document.indication_tags:
            allowed.update(_PERCENT.findall(document.body))
    return [token for token in _PERCENT.findall(query) if token not in allowed]


def _unapproved_doses(catalog: Catalog, query: str) -> list[str]:
    allowed: set[str] = set()
    for document in catalog.documents:
        if catalog.indication_id in document.indication_tags:
            allowed.update(_compact(token) for token in _DOSE.findall(document.body))
    return [token for token in _DOSE.findall(query) if _compact(token) not in allowed]


def _contains_phrase(text: str, phrase: str) -> bool:
    if not phrase:
        return False
    pattern = rf"(?<!\w){re.escape(phrase)}(?!\w)"
    return re.search(pattern, text, flags=re.IGNORECASE) is not None


def _compact(text: str) -> str:
    return re.sub(r"\s+", "", text).lower()
