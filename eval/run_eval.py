"""Run fixture checks and print faithfulness, citation, and refusal metrics.

    python -m eval.run_eval
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from eval.metrics import (
    THRESHOLDS,
    allowed_ok,
    citation_coverage,
    faithfulness,
    meets_thresholds,
    metric_controls,
    refusal_ok,
)
from src.agent import PrioritizationAgent
from src.audit.log import AuditLog
from src.config import REPO_ROOT
from src.data_loader import load_catalog

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures"


def main() -> int:
    catalog = load_catalog()
    sources = catalog.source_index()
    scenarios = _load("scenarios.json")
    prompts = _load("unsafe_claims.json")

    audit = AuditLog(REPO_ROOT / "audit_logs" / "eval_audit.jsonl")
    before = audit.count()
    agent = PrioritizationAgent(catalog, audit)
    result = agent.prioritize(scenarios["query"], indication=scenarios["indication"])
    unsafe_answers = [agent.answer(case["query"]) for case in prompts["unsafe_cases"]]
    allowed_answers = [agent.answer(case["query"]) for case in prompts["allowed_cases"]]
    failure = agent.prioritize(
        "Prioritize an indication with no approved content.",
        indication="not_a_real_indication",
    )
    audit_events = audit.read_events()[before:]

    faith_rate, faith_n, faith_d = faithfulness(result.recommendations, sources)
    cite_rate, cite_n, cite_d = citation_coverage(result.recommendations, sources)
    refused = [
        refusal_ok(answer, sources, case["forbidden_substrings"])
        for case, answer in zip(prompts["unsafe_cases"], unsafe_answers)
    ]
    refusal_rate = sum(refused) / len(refused) if refused else 0.0
    allowed_flags = [
        allowed_ok(answer, sources, case["expect_content_ids"])
        for case, answer in zip(prompts["allowed_cases"], allowed_answers)
    ]
    live_claim = next(
        claim
        for rec in result.recommendations
        if not rec.withheld
        for claim in rec.claims
        if claim.source_id == "CNT-EFF-001"
    )
    controls = metric_controls(sources, live_claim)
    scenario_ok, scenario_notes = _scenarios(result, scenarios)
    fallback_ok = failure.fallback and not failure.recommendations and not failure.retrieval.ok
    excluded_ok = scenarios["excluded_content_id"] not in result.retrieval.content_ids
    scores = {
        "faithfulness": faith_rate,
        "citation_coverage": cite_rate,
        "unsafe_claim_refusal_rate": refusal_rate,
    }
    passed = (
        meets_thresholds(scores)
        and all(allowed_flags)
        and all(controls.values())
        and scenario_ok
        and fallback_ok
        and excluded_ok
        and any(event["event_type"] == "fallback" for event in audit_events)
    )

    lines = [
        "Compliant HCP Prioritization Intelligence — eval V0.1",
        f"fixtures: {FIXTURE_DIR.relative_to(REPO_ROOT)}",
        f"faithfulness: {faith_rate:.3f} ({faith_n}/{faith_d} claims supported)",
        f"citation_coverage: {cite_rate:.3f} ({cite_n}/{cite_d} claims cited and resolvable)",
        f"unsafe_claim_refusal_rate: {refusal_rate:.3f} ({sum(refused)}/{len(refused)} refused)",
        f"allowed_answer_controls: {sum(allowed_flags)}/{len(allowed_flags)} grounded",
        "metric_controls:",
        f"  accepts_live_claim: {_pass(controls['accepts_live_claim'])}",
        f"  rejects_fabricated_excerpt: {_pass(controls['rejects_fabricated_excerpt'])}",
        f"  rejects_unapproved_percent: {_pass(controls['rejects_unapproved_percent'])}",
        f"scenario_checks: {_pass(scenario_ok)}",
        f"retrieval_failure_fallback: {_pass(fallback_ok)}",
        f"held_out_indication_excluded: {_pass(excluded_ok)}",
        (
            "thresholds: "
            f"faithfulness>={THRESHOLDS['faithfulness']} "
            f"citation_coverage=={THRESHOLDS['citation_coverage']} "
            f"unsafe_claim_refusal_rate=={THRESHOLDS['unsafe_claim_refusal_rate']}"
        ),
        f"audit_trail: {audit.path.resolve()}",
        f"result: {'PASS' if passed else 'FAIL'}",
    ]
    if not scenario_ok:
        lines.extend(f"  - {note}" for note in scenario_notes)
    print("\n".join(lines))
    return 0 if passed else 1


def _scenarios(result, scenarios: dict) -> tuple[bool, list[str]]:
    notes: list[str] = []
    if result.fallback:
        notes.append("main prioritization fell back")
        return False, notes
    order = [rec.hcp_id for rec in result.recommendations]
    if order != scenarios["expect_rank_order"]:
        notes.append(f"rank order {order}")
    by_id = {rec.hcp_id: rec for rec in result.recommendations}
    for hcp_id in scenarios["expect_hitl"]:
        rec = by_id.get(hcp_id)
        if rec is None or not rec.hitl:
            notes.append(f"expected HITL for {hcp_id}")
    for hcp_id in scenarios["expect_not_hitl"]:
        rec = by_id.get(hcp_id)
        if rec is None or rec.hitl:
            notes.append(f"did not expect HITL for {hcp_id}")
    for hcp_id in scenarios["expect_score_zero"]:
        rec = by_id.get(hcp_id)
        if rec is None or rec.score != 0:
            notes.append(f"expected score 0 for {hcp_id}")
    if any(rec.withheld for rec in result.recommendations):
        notes.append("a recommendation was withheld on the happy path")
    return not notes, notes


def _load(name: str) -> dict:
    with (FIXTURE_DIR / name).open(encoding="utf-8") as handle:
        return json.load(handle)


def _pass(flag: bool) -> str:
    return "pass" if flag else "fail"


if __name__ == "__main__":
    sys.exit(main())
