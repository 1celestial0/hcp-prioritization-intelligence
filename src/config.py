"""Frozen demo settings. Dates do not follow the wall clock."""

from __future__ import annotations

from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = REPO_ROOT / "data" / "synthetic"
DEFAULT_AUDIT_PATH = REPO_ROOT / "audit_logs" / "prioritization_audit.jsonl"

AS_OF = date(2026, 3, 15)
ENGAGEMENT_WINDOW_DAYS = 180
HITL_CONFIDENCE_THRESHOLD = 0.62

PRODUCT = "Lumivex"
MANUFACTURER = "HelioSynth Therapeutics"

FALLBACK_MESSAGE = (
    "Retrieval failed: no approved content matched the indication. "
    "Recommendations withheld. Nothing was invented."
)

ID_PREFIXES = {
    "hcp": "HCP-SYN-",
    "interaction": "INT-",
    "content": "CNT-",
    "rule": "RULE-",
    "territory": "TR-",
}

TIER_POINTS = {"A": 15, "B": 10, "C": 5}
OUTCOME_POINTS = {
    "requested_info": 12,
    "engaged": 8,
    "no_response": 2,
    "declined": -8,
}
POSITIVE_CONTENT_OUTCOMES = {"requested_info", "engaged"}
CONTENT_BONUS = 6
ENGAGEMENT_CAP = 35

APPROVED_SPECIALTIES = {"pulmonology", "allergy and immunology"}
LIMITED_SPECIALTIES = {"internal medicine"}
