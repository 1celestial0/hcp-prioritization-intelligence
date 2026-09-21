"""Single-purpose offline agent: plan, retrieve, rank, ground, answer.

The default path never calls a model API. If HCP_LLM_MODE is set to anything
other than offline, the run still uses the deterministic templates and records
an llm_fallback audit event.
"""

from __future__ import annotations

import os

from src.audit.log import AuditLog
from src.config import AS_OF, FALLBACK_MESSAGE
from src.models import Catalog, PrioritizationResult, QueryAnswer
from src.ranking.rank import rank_hcps
from src.retrieval.retrieve import retrieve_content
from src.safety.grounding import enforce_grounding
from src.safety.guard import answer_query


class PrioritizationAgent:
    def __init__(self, catalog: Catalog, audit: AuditLog) -> None:
        self.catalog = catalog
        self.audit = audit
        self._runtime_noted = False

    def prioritize(
        self,
        query: str,
        *,
        indication: str | None = None,
    ) -> PrioritizationResult:
        self._note_runtime()
        indication_id = indication or self.catalog.indication_id
        self.audit.append(
            "plan",
            query=query,
            indication=indication_id,
            product=self.catalog.product,
            as_of=AS_OF.isoformat(),
            mode="offline",
        )
        retrieval = retrieve_content(
            self.catalog,
            indication=indication_id,
            query=query,
            top_k=6,
        )
        self.audit.append(
            "retrieval",
            ok=retrieval.ok,
            indication=indication_id,
            content_ids=retrieval.content_ids,
            scores=[
                {"content_id": item.document.content_id, "score": item.score}
                for item in retrieval.docs
            ],
            fallback_reason=retrieval.fallback_reason,
        )
        if not retrieval.ok:
            message = retrieval.fallback_reason or FALLBACK_MESSAGE
            self.audit.append(
                "fallback",
                indication=indication_id,
                message=message,
                recommendations_withheld=True,
            )
            return PrioritizationResult(
                query=query,
                indication=indication_id,
                retrieval=retrieval,
                recommendations=[],
                fallback=True,
                fallback_message=message,
            )

        ranked = rank_hcps(self.catalog, retrieval, as_of=AS_OF)
        grounded = enforce_grounding(ranked, self.catalog.source_index())
        withheld = [rec.hcp_id for rec in grounded if rec.withheld]
        self.audit.append(
            "ranking",
            indication=indication_id,
            order=[rec.hcp_id for rec in grounded],
            withheld=withheld,
            hitl=[rec.hcp_id for rec in grounded if rec.hitl],
            recommendations=[
                {
                    "hcp_id": rec.hcp_id,
                    "rank": rec.rank,
                    "score": rec.score,
                    "confidence": rec.confidence,
                    "hitl": rec.hitl,
                    "hitl_reasons": rec.hitl_reasons,
                    "citations": [claim.source_id for claim in rec.claims],
                    "withheld": rec.withheld,
                }
                for rec in grounded
            ],
        )
        if withheld:
            self.audit.append(
                "grounding_failure",
                hcp_ids=withheld,
                message="One or more recommendations were withheld instead of returned ungrounded.",
            )
        return PrioritizationResult(
            query=query,
            indication=indication_id,
            retrieval=retrieval,
            recommendations=grounded,
            fallback=False,
        )

    def answer(self, query: str) -> QueryAnswer:
        self._note_runtime()
        result = answer_query(self.catalog, query)
        event_type = "query_fallback" if result.fallback else "query_refusal" if result.refused else "query_answer"
        self.audit.append(
            event_type,
            query=query,
            refused=result.refused,
            fallback=result.fallback,
            hitl=result.hitl,
            rule_id=result.rule_id,
            citations=[claim.source_id for claim in result.claims],
            reason=result.reason,
        )
        return result

    def _note_runtime(self) -> None:
        if self._runtime_noted:
            return
        self._runtime_noted = True
        requested = os.environ.get("HCP_LLM_MODE", "offline").strip().lower() or "offline"
        if requested in {"offline", "deterministic"}:
            self.audit.append("runtime", mode="offline")
            return
        self.audit.append(
            "llm_fallback",
            requested=requested,
            used="offline",
            message="External LLM mode is optional and not required. Using deterministic offline answers.",
        )
