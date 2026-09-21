from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.audit.log import AuditLog
from src.data_loader import load_catalog
from src.models import DataError


def test_catalog_loads_synthetic_roster(catalog):
    assert len(catalog.hcps) == 12
    assert catalog.product == "Lumivex"
    assert catalog.indication_id == "virellic_syndrome"
    assert "CNT-EFF-001" in catalog.content_by_id
    assert catalog.content_by_id["CNT-EFF-001"].spans["efficacy"] in catalog.content_by_id["CNT-EFF-001"].body


def test_loader_rejects_npi_like_value(tmp_path: Path):
    _copy_synthetic(tmp_path)
    roster = tmp_path / "hcp_roster.csv"
    text = roster.read_text(encoding="utf-8")
    roster.write_text(text.replace("HCP-SYN-0142", "1234567890"), encoding="utf-8")
    with pytest.raises(DataError, match="NPI-like"):
        load_catalog(tmp_path)


def test_loader_rejects_span_not_in_body(tmp_path: Path):
    _copy_synthetic(tmp_path)
    path = tmp_path / "approved_content.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["documents"][0]["spans"]["indication"] = "This sentence was never approved."
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(DataError, match="not verbatim"):
        load_catalog(tmp_path)


def test_audit_log_is_append_only(tmp_path: Path):
    log = AuditLog(tmp_path / "audit.jsonl")
    log.append("retrieval", ok=True, content_ids=["CNT-IDN-001"])
    first = (tmp_path / "audit.jsonl").read_text(encoding="utf-8")
    log.append("fallback", message="Recommendations withheld.")
    second = (tmp_path / "audit.jsonl").read_text(encoding="utf-8")
    assert second.startswith(first)
    assert first.count("\n") == 1
    events = log.read_events()
    assert [event["event_type"] for event in events] == ["retrieval", "fallback"]
    assert events[0]["ok"] is True


def _copy_synthetic(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1] / "data" / "synthetic"
    for name in ("hcp_roster.csv", "interactions.csv", "approved_content.json", "claim_rules.json"):
        (tmp_path / name).write_text((root / name).read_text(encoding="utf-8"), encoding="utf-8")
