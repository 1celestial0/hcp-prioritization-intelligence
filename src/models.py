"""Shared records for the offline prioritization flow."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date


class DataError(Exception):
    """Synthetic data failed a public-safe or schema check."""


@dataclass(frozen=True)
class HCP:
    hcp_id: str
    display_name: str
    specialty: str
    tier: str
    territory_id: str
    practice_setting: str
    panel_focus: str
    years_in_practice: int

    def text(self) -> str:
        return (
            f"{self.hcp_id} {self.display_name} specialty {self.specialty} "
            f"tier {self.tier} territory {self.territory_id} "
            f"practice {self.practice_setting} panel_focus {self.panel_focus}"
        )


@dataclass(frozen=True)
class Interaction:
    interaction_id: str
    hcp_id: str
    interaction_date: date
    channel: str
    content_id: str | None
    outcome: str
    note: str

    def text(self) -> str:
        content = self.content_id or "none"
        return (
            f"{self.interaction_id} on {self.interaction_date.isoformat()} "
            f"via {self.channel} outcome {self.outcome} content {content}. {self.note}"
        )


@dataclass(frozen=True)
class ContentDoc:
    content_id: str
    title: str
    indication_tags: list[str]
    audiences: list[str]
    version: str
    claim_ids: list[str]
    body: str
    spans: dict[str, str]

    def text(self) -> str:
        return f"{self.title}\n{self.body}"


@dataclass(frozen=True)
class AllowedClaim:
    rule_id: str
    content_id: str
    span: str
    requires_fair_balance: bool
    reason: str
    fair_balance_content_id: str | None = None
    fair_balance_span: str | None = None

    def text(self) -> str:
        return f"{self.rule_id}: {self.reason}"


@dataclass(frozen=True)
class ProhibitedRule:
    rule_id: str
    patterns: list[str]
    reason: str
    safe_content_id: str | None = None
    safe_span: str | None = None

    def text(self) -> str:
        return f"{self.rule_id}: {self.reason}"


@dataclass(frozen=True)
class AudienceRule:
    rule_id: str
    text_value: str
    approved_audiences: list[str]
    population: str
    indication_id: str
    indication_label: str

    def text(self) -> str:
        return self.text_value


@dataclass
class Catalog:
    hcps: list[HCP]
    interactions: list[Interaction]
    documents: list[ContentDoc]
    allowed_claims: list[AllowedClaim]
    prohibited_rules: list[ProhibitedRule]
    audience_rule: AudienceRule
    product: str
    indication_id: str
    indication_label: str

    def __post_init__(self) -> None:
        self.hcp_by_id = {h.hcp_id: h for h in self.hcps}
        self.content_by_id = {d.content_id: d for d in self.documents}
        self.allowed_by_id = {r.rule_id: r for r in self.allowed_claims}
        self.prohibited_by_id = {r.rule_id: r for r in self.prohibited_rules}
        grouped: dict[str, list[Interaction]] = {h.hcp_id: [] for h in self.hcps}
        for interaction in self.interactions:
            grouped.setdefault(interaction.hcp_id, []).append(interaction)
        for rows in grouped.values():
            rows.sort(key=lambda row: row.interaction_date, reverse=True)
        self.interactions_by_hcp = grouped

    def source_index(self) -> dict[str, str]:
        index: dict[str, str] = {}
        for hcp in self.hcps:
            index[hcp.hcp_id] = hcp.text()
        for interaction in self.interactions:
            index[interaction.interaction_id] = interaction.text()
        for doc in self.documents:
            index[doc.content_id] = doc.text()
        for rule in self.allowed_claims:
            index[rule.rule_id] = rule.text()
        for rule in self.prohibited_rules:
            index[rule.rule_id] = rule.text()
        index[self.audience_rule.rule_id] = self.audience_rule.text()
        return index

    def span(self, content_id: str, span_name: str) -> str:
        doc = self.content_by_id.get(content_id)
        if doc is None or span_name not in doc.spans:
            raise DataError(f"Missing approved span {content_id}:{span_name}")
        return doc.spans[span_name]


@dataclass(frozen=True)
class Claim:
    statement: str
    source_type: str
    source_id: str
    excerpt: str


@dataclass
class Recommendation:
    hcp_id: str
    display_name: str
    specialty: str
    tier: str
    territory_id: str
    rank: int
    score: int
    confidence: float
    hitl: bool
    hitl_reasons: list[str]
    claims: list[Claim]
    components: dict[str, int]
    withheld: bool = False
    withhold_reason: str | None = None


@dataclass
class RetrievedDoc:
    document: ContentDoc
    score: float


@dataclass
class RetrievalResult:
    ok: bool
    indication: str
    query: str
    docs: list[RetrievedDoc] = field(default_factory=list)
    fallback_reason: str | None = None

    @property
    def content_ids(self) -> list[str]:
        return [item.document.content_id for item in self.docs]


@dataclass
class PrioritizationResult:
    query: str
    indication: str
    retrieval: RetrievalResult
    recommendations: list[Recommendation]
    fallback: bool
    fallback_message: str | None = None


@dataclass
class QueryAnswer:
    query: str
    refused: bool
    fallback: bool
    hitl: bool
    rule_id: str | None
    reason: str
    claims: list[Claim]
    rendered: str
    hitl_reason: str | None = None
