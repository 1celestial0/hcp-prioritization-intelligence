"""Load and validate the synthetic commercial files."""

from __future__ import annotations

import csv
import json
import re
from datetime import date
from pathlib import Path

from src.config import DATA_DIR, ID_PREFIXES, OUTCOME_POINTS, TIER_POINTS
from src.models import (
    AllowedClaim,
    AudienceRule,
    Catalog,
    ContentDoc,
    DataError,
    HCP,
    Interaction,
    ProhibitedRule,
)

NPI_LIKE = re.compile(r"^\d{10}$")
REQUIRED_HCP = {
    "hcp_id",
    "display_name",
    "specialty",
    "tier",
    "territory_id",
    "practice_setting",
    "panel_focus",
    "years_in_practice",
}
REQUIRED_INTERACTION = {
    "interaction_id",
    "hcp_id",
    "interaction_date",
    "channel",
    "content_id",
    "outcome",
    "note",
}


def load_catalog(data_dir: Path | None = None) -> Catalog:
    root = data_dir or DATA_DIR
    hcps = _load_hcps(root / "hcp_roster.csv")
    documents = _load_content(root / "approved_content.json")
    interactions = _load_interactions(root / "interactions.csv", hcps, documents)
    rules_payload = _read_json(root / "claim_rules.json")
    allowed, prohibited, audience, product, indication_id, indication_label = _load_rules(
        rules_payload, documents
    )
    return Catalog(
        hcps=hcps,
        interactions=interactions,
        documents=documents,
        allowed_claims=allowed,
        prohibited_rules=prohibited,
        audience_rule=audience,
        product=product,
        indication_id=indication_id,
        indication_label=indication_label,
    )


def _read_json(path: Path) -> dict:
    if not path.exists():
        raise DataError(f"Missing synthetic file: {path}")
    with path.open(encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise DataError(f"Expected object in {path}")
    return payload


def _reject_unsafe_token(value: str, context: str) -> None:
    token = value.strip()
    if NPI_LIKE.match(token):
        raise DataError(f"Refusing NPI-like value in {context}")


def _require_prefix(value: str, prefix: str, context: str) -> None:
    if not value.startswith(prefix):
        raise DataError(f"{context} must start with {prefix}: {value}")


def _load_hcps(path: Path) -> list[HCP]:
    if not path.exists():
        raise DataError(f"Missing synthetic file: {path}")
    hcps: list[HCP] = []
    seen: set[str] = set()
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        missing = REQUIRED_HCP - set(reader.fieldnames or [])
        if missing:
            raise DataError(f"Roster missing columns: {sorted(missing)}")
        for row in reader:
            for key, value in row.items():
                if value is not None:
                    _reject_unsafe_token(str(value), f"roster.{key}")
            hcp_id = row["hcp_id"].strip()
            _require_prefix(hcp_id, ID_PREFIXES["hcp"], "hcp_id")
            _require_prefix(row["territory_id"].strip(), ID_PREFIXES["territory"], "territory_id")
            if hcp_id in seen:
                raise DataError(f"Duplicate hcp_id {hcp_id}")
            seen.add(hcp_id)
            tier = row["tier"].strip()
            if tier not in TIER_POINTS:
                raise DataError(f"Unknown tier {tier} on {hcp_id}")
            hcps.append(
                HCP(
                    hcp_id=hcp_id,
                    display_name=row["display_name"].strip(),
                    specialty=row["specialty"].strip(),
                    tier=tier,
                    territory_id=row["territory_id"].strip(),
                    practice_setting=row["practice_setting"].strip(),
                    panel_focus=row["panel_focus"].strip(),
                    years_in_practice=int(row["years_in_practice"]),
                )
            )
    if not hcps:
        raise DataError("Roster is empty")
    return hcps


def _load_content(path: Path) -> list[ContentDoc]:
    payload = _read_json(path)
    documents: list[ContentDoc] = []
    seen: set[str] = set()
    for raw in payload.get("documents", []):
        content_id = str(raw["content_id"]).strip()
        _require_prefix(content_id, ID_PREFIXES["content"], "content_id")
        _reject_unsafe_token(content_id, "content_id")
        if content_id in seen:
            raise DataError(f"Duplicate content_id {content_id}")
        seen.add(content_id)
        body = str(raw["body"])
        spans = {str(k): str(v) for k, v in raw.get("spans", {}).items()}
        for name, excerpt in spans.items():
            if excerpt not in body:
                raise DataError(f"Span {content_id}:{name} is not verbatim in the body")
            if len(excerpt) < 12:
                raise DataError(f"Span {content_id}:{name} is too short to cite")
        documents.append(
            ContentDoc(
                content_id=content_id,
                title=str(raw["title"]).strip(),
                indication_tags=[str(tag) for tag in raw.get("indication_tags", [])],
                audiences=[str(item) for item in raw.get("audiences", [])],
                version=str(raw.get("version", "")),
                claim_ids=[str(item) for item in raw.get("claim_ids", [])],
                body=body,
                spans=spans,
            )
        )
    if not documents:
        raise DataError("Approved content corpus is empty")
    return documents


def _load_interactions(
    path: Path,
    hcps: list[HCP],
    documents: list[ContentDoc],
) -> list[Interaction]:
    if not path.exists():
        raise DataError(f"Missing synthetic file: {path}")
    known_hcps = {hcp.hcp_id for hcp in hcps}
    known_content = {doc.content_id for doc in documents}
    interactions: list[Interaction] = []
    seen: set[str] = set()
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        missing = REQUIRED_INTERACTION - set(reader.fieldnames or [])
        if missing:
            raise DataError(f"Interactions missing columns: {sorted(missing)}")
        for row in reader:
            for key, value in row.items():
                if value:
                    _reject_unsafe_token(str(value), f"interaction.{key}")
            interaction_id = row["interaction_id"].strip()
            _require_prefix(interaction_id, ID_PREFIXES["interaction"], "interaction_id")
            if interaction_id in seen:
                raise DataError(f"Duplicate interaction_id {interaction_id}")
            seen.add(interaction_id)
            hcp_id = row["hcp_id"].strip()
            if hcp_id not in known_hcps:
                raise DataError(f"{interaction_id} references unknown {hcp_id}")
            content_raw = (row.get("content_id") or "").strip()
            content_id = content_raw or None
            if content_id is not None and content_id not in known_content:
                raise DataError(f"{interaction_id} references unknown content {content_id}")
            outcome = row["outcome"].strip()
            if outcome not in OUTCOME_POINTS:
                raise DataError(f"Unknown outcome {outcome} on {interaction_id}")
            interactions.append(
                Interaction(
                    interaction_id=interaction_id,
                    hcp_id=hcp_id,
                    interaction_date=date.fromisoformat(row["interaction_date"].strip()),
                    channel=row["channel"].strip(),
                    content_id=content_id,
                    outcome=outcome,
                    note=row["note"].strip(),
                )
            )
    return interactions


def _load_rules(
    payload: dict,
    documents: list[ContentDoc],
) -> tuple[list[AllowedClaim], list[ProhibitedRule], AudienceRule, str, str, str]:
    indication = payload["indication"]
    audience_raw = payload["audience_rule"]
    audience = AudienceRule(
        rule_id=str(audience_raw["rule_id"]),
        text_value=str(audience_raw["text"]),
        approved_audiences=[str(item) for item in indication["approved_audiences"]],
        population=str(indication["population"]),
        indication_id=str(indication["id"]),
        indication_label=str(indication["label"]),
    )
    _require_prefix(audience.rule_id, ID_PREFIXES["rule"], "rule_id")
    if audience.text_value.strip() == "":
        raise DataError("Audience rule text is empty")

    known_content = {doc.content_id: doc for doc in documents}
    allowed: list[AllowedClaim] = []
    for raw in payload.get("allowed_claims", []):
        rule = AllowedClaim(
            rule_id=str(raw["rule_id"]),
            content_id=str(raw["content_id"]),
            span=str(raw["span"]),
            requires_fair_balance=bool(raw.get("requires_fair_balance", False)),
            reason=str(raw["reason"]),
            fair_balance_content_id=raw.get("fair_balance_content_id"),
            fair_balance_span=raw.get("fair_balance_span"),
        )
        _require_prefix(rule.rule_id, ID_PREFIXES["rule"], "rule_id")
        _assert_span(known_content, rule.content_id, rule.span, rule.rule_id)
        if rule.requires_fair_balance:
            if not rule.fair_balance_content_id or not rule.fair_balance_span:
                raise DataError(f"{rule.rule_id} requires fair balance but has no target")
            _assert_span(
                known_content,
                rule.fair_balance_content_id,
                rule.fair_balance_span,
                rule.rule_id,
            )
        allowed.append(rule)

    prohibited: list[ProhibitedRule] = []
    for raw in payload.get("prohibited_patterns", []):
        rule = ProhibitedRule(
            rule_id=str(raw["rule_id"]),
            patterns=[str(item) for item in raw.get("patterns", [])],
            reason=str(raw["reason"]),
            safe_content_id=raw.get("safe_content_id"),
            safe_span=raw.get("safe_span"),
        )
        _require_prefix(rule.rule_id, ID_PREFIXES["rule"], "rule_id")
        if len(rule.reason) < 12:
            raise DataError(f"{rule.rule_id} reason is too short to cite")
        if rule.safe_content_id or rule.safe_span:
            _assert_span(
                known_content,
                str(rule.safe_content_id),
                str(rule.safe_span),
                rule.rule_id,
            )
        prohibited.append(rule)

    return (
        allowed,
        prohibited,
        audience,
        str(payload.get("product", "")),
        str(indication["id"]),
        str(indication["label"]),
    )


def _assert_span(
    documents: dict[str, ContentDoc],
    content_id: str,
    span_name: str,
    rule_id: str,
) -> None:
    doc = documents.get(content_id)
    if doc is None:
        raise DataError(f"{rule_id} references unknown content {content_id}")
    excerpt = doc.spans.get(span_name)
    if excerpt is None or excerpt not in doc.body:
        raise DataError(f"{rule_id} span {content_id}:{span_name} is not in the corpus")
