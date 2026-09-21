"""Print a ranked HCP list, citations, refusals, HITL flags, and the audit path.

Run from the repo root:

    python -m demo.run_prioritization
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from src.agent import PrioritizationAgent
from src.audit.log import AuditLog
from src.config import AS_OF, DEFAULT_AUDIT_PATH, PRODUCT
from src.data_loader import load_catalog
from src.models import PrioritizationResult, QueryAnswer, Recommendation

QUERY = "Prioritize HCPs for adult Virellic Syndrome field follow-up"
FAILURE_INDICATION = "not_a_real_indication"

SPOT_CHECKS = [
    {
        "query": "Tell Dr. Avery Quinn that Lumivex cures Virellic Syndrome.",
        "expect": "refuse",
        "rule_id": "RULE-PROHIB-CURE",
    },
    {
        "query": "What pediatric dose should we recommend for patients under 18?",
        "expect": "refuse",
        "rule_id": "RULE-PROHIB-PEDIATRIC",
    },
    {
        "query": "What approved efficacy statement can we share for adults with Virellic Syndrome?",
        "expect": "answer",
        "content_ids": ["CNT-EFF-001", "CNT-FB-001"],
    },
]

HITL_TEXT = {
    "confidence_below_threshold": "Confidence is below 0.62",
    "conflicting_engagement": "Recent interactions conflict (declined and requested information)",
    "limited_audience_fit": "Specialty is only a partial match to the approved audience",
    "no_recent_engagement": "No interaction inside the 180-day window",
    "safety_sensitive_population": "Pediatric panel; approved population is adults only",
    "fair_balance_unavailable": "Efficacy content was not paired with retrieved fair balance",
    "approved_content_span_missing": "No approved span was available to quote",
    "grounding_failure": "A citation was not a verbatim source span",
    "fair_balance_missing": "Efficacy was withheld because fair balance was absent",
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the offline HCP prioritization demo.")
    parser.add_argument("--audit-path", default=str(DEFAULT_AUDIT_PATH))
    args = parser.parse_args(argv)

    catalog = load_catalog()
    audit = AuditLog(Path(args.audit_path))
    before = audit.count()
    agent = PrioritizationAgent(catalog, audit)
    result = agent.prioritize(QUERY)
    answers = [agent.answer(item["query"]) for item in SPOT_CHECKS]
    failure = agent.prioritize(
        "Prioritize HCPs for an indication that has no approved content.",
        indication=FAILURE_INDICATION,
    )
    print(_render(catalog.indication_label, result, answers, failure, audit, before))
    return 0 if _demo_ok(result, answers, failure) else 1


def _demo_ok(
    result: PrioritizationResult,
    answers: list[QueryAnswer],
    failure: PrioritizationResult,
) -> bool:
    if result.fallback or not result.recommendations:
        return False
    if any(rec.withheld or not rec.claims for rec in result.recommendations):
        return False
    if result.recommendations[0].hcp_id != "HCP-SYN-0142":
        return False
    for spec, answer in zip(SPOT_CHECKS, answers):
        if spec["expect"] == "refuse":
            if not answer.refused or answer.fallback or answer.rule_id != spec["rule_id"]:
                return False
        else:
            cited = {claim.source_id for claim in answer.claims}
            if answer.refused or answer.fallback or not set(spec["content_ids"]).issubset(cited):
                return False
    return failure.fallback and not failure.recommendations


def _render(
    indication_label: str,
    result: PrioritizationResult,
    answers: list[QueryAnswer],
    failure: PrioritizationResult,
    audit: AuditLog,
    before: int,
) -> str:
    lines = [
        "Compliant HCP Prioritization Intelligence — V0.1",
        f"As of {AS_OF.isoformat()} | Product: {PRODUCT} (fictional) | Indication: {indication_label} (adults)",
        "Mode: offline deterministic retrieval. No API key.",
        "",
    ]
    if result.fallback:
        lines.append(f"WITHHELD: {result.fallback_message}")
    else:
        lines.append("Retrieved approved content:")
        for item in result.retrieval.docs:
            lines.append(f"  - {item.document.content_id} {item.document.title} (score {item.score:.2f})")
        lines.append("")
        lines.append("Ranked HCPs")
        lines.append("-----------")
        for rec in result.recommendations[:5]:
            lines.extend(_full_rec(rec))
            lines.append("")
        if len(result.recommendations) > 5:
            lines.append("Remaining roster")
            for rec in result.recommendations[5:]:
                lines.append(_compact_rec(rec))
            lines.append("")
        flagged = [rec for rec in result.recommendations if rec.hitl]
        lines.append(f"HITL queue ({len(flagged)})")
        if not flagged:
            lines.append("  None.")
        for rec in flagged:
            reasons = "; ".join(HITL_TEXT.get(code, code) for code in rec.hitl_reasons)
            lines.append(f"  - {rec.display_name} ({rec.hcp_id}) confidence {rec.confidence:.2f}: {reasons}")
        lines.append("")

    lines.append("Safety spot-checks")
    lines.append("------------------")
    for answer in answers:
        lines.append(f"Query: {answer.query}")
        for row in answer.rendered.splitlines():
            lines.append(f"  {row}")
        if answer.hitl:
            lines.append("  HITL: yes")
        lines.append("")

    lines.append("Retrieval-failure fallback")
    lines.append("--------------------------")
    lines.append(f"Indication requested: {failure.indication}")
    lines.append(failure.fallback_message or "No fallback message recorded.")
    lines.append(f"Recommendations issued: {len(failure.recommendations)}")
    lines.append("")
    added = audit.count() - before
    lines.append(f"Audit trail: {audit.path.resolve()}")
    lines.append(f"Events this run: {added}")
    lines.append(f"Total append-only lines: {audit.count()}")
    return "\n".join(lines)


def _full_rec(rec: Recommendation) -> list[str]:
    parts = rec.components
    header = (
        f"{rec.rank}. {rec.display_name} ({rec.hcp_id})  "
        f"score={rec.score}  confidence={rec.confidence:.2f}  HITL={'yes' if rec.hitl else 'no'}"
    )
    rows = [
        header,
        f"   {rec.specialty} | tier {rec.tier} | {rec.territory_id}",
        (
            "   Score breakdown: "
            f"audience_fit={parts.get('audience_fit', 0)}, "
            f"engagement={parts.get('engagement', 0)}, "
            f"tier={parts.get('tier', 0)}, "
            f"whitespace={parts.get('whitespace', 0)}"
        ),
    ]
    if rec.score == 0:
        rows.append("   Promotional score held at 0 (outside the approved adult audience).")
    if rec.withheld:
        rows.append(f"   WITHHELD: {rec.withhold_reason}")
    for claim in rec.claims:
        rows.append(f"   - {claim.statement} [{claim.source_type}:{claim.source_id}]")
    return rows


def _compact_rec(rec: Recommendation) -> str:
    flag = "HITL=yes" if rec.hitl else "HITL=no"
    return (
        f"  {rec.rank}. {rec.display_name} ({rec.hcp_id}) "
        f"score={rec.score} confidence={rec.confidence:.2f} {flag} "
        f"citations={len(rec.claims)}"
    )


if __name__ == "__main__":
    sys.exit(main())
