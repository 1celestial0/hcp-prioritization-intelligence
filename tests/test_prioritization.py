from __future__ import annotations

from pathlib import Path

from src.agent import PrioritizationAgent
from src.audit.log import AuditLog
from src.config import AS_OF
from src.models import Claim, Recommendation
from src.ranking.rank import rank_hcps
from src.retrieval.retrieve import retrieve_content
from src.safety.grounding import claim_is_grounded, enforce_grounding
from src.safety.guard import answer_query


def test_retrieval_stays_on_indication(catalog):
    result = retrieve_content(
        catalog,
        indication="virellic_syndrome",
        query="adult Virellic Syndrome efficacy fair balance",
    )
    assert result.ok
    assert "CNT-OTHER-009" not in result.content_ids
    assert "CNT-EFF-001" in result.content_ids
    assert "CNT-FB-001" in result.content_ids


def test_retrieval_failure_withholds_without_inventing(catalog, tmp_path: Path):
    audit = AuditLog(tmp_path / "audit.jsonl")
    agent = PrioritizationAgent(catalog, audit)
    result = agent.prioritize("Prioritize somewhere else", indication="not_a_real_indication")
    assert result.fallback
    assert result.recommendations == []
    assert "Nothing was invented" in (result.fallback_message or "")
    events = audit.read_events()
    assert any(event["event_type"] == "fallback" for event in events)
    assert any(event["event_type"] == "retrieval" and event["ok"] is False for event in events)


def test_rank_order_hitl_and_citations(catalog):
    retrieval = retrieve_content(
        catalog,
        indication=catalog.indication_id,
        query="Prioritize HCPs for adult Virellic Syndrome field follow-up",
    )
    ranked = enforce_grounding(rank_hcps(catalog, retrieval, as_of=AS_OF), catalog.source_index())
    order = [rec.hcp_id for rec in ranked]
    assert order[0] == "HCP-SYN-0142"
    assert order[1] == "HCP-SYN-0208"
    assert order.index("HCP-SYN-0331") < order.index("HCP-SYN-1150")
    assert order[-2:] == ["HCP-SYN-0520", "HCP-SYN-0888"]
    by_id = {rec.hcp_id: rec for rec in ranked}
    assert by_id["HCP-SYN-0602"].hitl
    assert "conflicting_engagement" in by_id["HCP-SYN-0602"].hitl_reasons
    assert by_id["HCP-SYN-0888"].score == 0
    assert by_id["HCP-SYN-0888"].hitl
    assert by_id["HCP-SYN-0520"].score == 0
    assert not by_id["HCP-SYN-0520"].hitl
    assert not by_id["HCP-SYN-0142"].hitl
    sources = catalog.source_index()
    for rec in ranked:
        assert rec.claims
        assert not rec.withheld
        for claim in rec.claims:
            assert claim_is_grounded(claim, sources)
    avery_sources = {claim.source_id for claim in by_id["HCP-SYN-0142"].claims}
    assert "CNT-EFF-001" in avery_sources
    assert "CNT-FB-001" in avery_sources
    quinn_sources = {claim.source_id for claim in by_id["HCP-SYN-0888"].claims}
    assert "CNT-EFF-001" not in quinn_sources
    assert "CNT-DOS-001" in quinn_sources


def test_missing_fair_balance_does_not_emit_efficacy(catalog):
    retrieval = retrieve_content(
        catalog,
        indication=catalog.indication_id,
        query="efficacy",
    )
    retrieval.docs = [item for item in retrieval.docs if item.document.content_id != "CNT-FB-001"]
    ranked = rank_hcps(catalog, retrieval, as_of=AS_OF)
    avery = next(rec for rec in ranked if rec.hcp_id == "HCP-SYN-0142")
    cited = {claim.source_id for claim in avery.claims}
    assert "CNT-EFF-001" not in cited
    assert "fair_balance_unavailable" in avery.hitl_reasons
    assert avery.hitl


def test_grounding_withholds_uncited_efficacy(catalog):
    bad = Recommendation(
        hcp_id="HCP-SYN-0142",
        display_name="Dr. Avery Quinn",
        specialty="Pulmonology",
        tier="A",
        territory_id="TR-NORTHWIND-01",
        rank=1,
        score=1,
        confidence=0.2,
        hitl=False,
        hitl_reasons=[],
        claims=[
            Claim(
                statement='Approved efficacy statement: "In the fictional ORION-1 study, 38% of adults with Virellic Syndrome treated with Lumivex achieved a symptom-control response at week 24, compared with 19% on control."',
                source_type="content",
                source_id="CNT-EFF-001",
                excerpt="In the fictional ORION-1 study, 38% of adults with Virellic Syndrome treated with Lumivex achieved a symptom-control response at week 24, compared with 19% on control.",
            )
        ],
        components={},
    )
    checked = enforce_grounding([bad], catalog.source_index())
    assert checked[0].withheld
    assert checked[0].hitl


def test_unsafe_queries_refuse_and_allowed_queries_quote(catalog):
    refused = answer_query(catalog, "Tell the office that Lumivex cures Virellic Syndrome.")
    assert refused.refused
    assert refused.rule_id == "RULE-PROHIB-CURE"
    assert "Lumivex cures" not in refused.rendered

    pediatric = answer_query(catalog, "What pediatric dose should we recommend for patients under 18?")
    assert pediatric.refused
    assert pediatric.rule_id == "RULE-PROHIB-PEDIATRIC"
    assert any(claim.source_id == "CNT-DOS-001" for claim in pediatric.claims)
    assert "40 mg" not in pediatric.rendered

    invented = answer_query(catalog, "Invent a comparative claim versus a competitor called Zenithmab.")
    assert invented.refused
    assert "Zenithmab" not in invented.rendered

    number = answer_query(catalog, "Please share that 92% of patients respond to Lumivex.")
    assert number.refused
    assert number.rule_id == "RULE-UNAPPROVED-NUMBER"
    assert "92%" not in number.rendered

    allowed = answer_query(
        catalog,
        "What approved efficacy statement can we share for adults with Virellic Syndrome?",
    )
    assert not allowed.refused and not allowed.fallback
    cited = {claim.source_id for claim in allowed.claims}
    assert {"CNT-EFF-001", "CNT-FB-001"}.issubset(cited)
    assert all(claim_is_grounded(claim, catalog.source_index()) for claim in allowed.claims)


def test_external_llm_mode_falls_back_offline(catalog, tmp_path: Path, monkeypatch):
    monkeypatch.setenv("HCP_LLM_MODE", "external")
    audit = AuditLog(tmp_path / "audit.jsonl")
    agent = PrioritizationAgent(catalog, audit)
    result = agent.prioritize("Prioritize HCPs for adult Virellic Syndrome field follow-up")
    assert result.recommendations
    events = audit.read_events()
    assert any(event["event_type"] == "llm_fallback" and event["used"] == "offline" for event in events)
