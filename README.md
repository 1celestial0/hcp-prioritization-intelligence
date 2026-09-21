# Compliant HCP Prioritization Intelligence (V0.1)

Public-safe portfolio thin slice for FDE / Databricks interviews: **Discovery → Data Reality → Production**.

Synthetic pharma commercial data only. No real Jazz/client/HCP/PHI identifiers.

## Demo path (target)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m demo.run_prioritization
python -m eval.run_eval
```

## Layout

| Path | Role |
|------|------|
| `data/synthetic/` | HCP roster, interactions, approved content, indication/fair-balance rules |
| `src/retrieval/` | Retrieve + ground against approved corpus |
| `src/ranking/` | Rank HCPs with cited evidence |
| `src/safety/` | Refuse ungrounded medical claims; HITL on low confidence |
| `src/audit/` | Audit log + retrieval-failure fallback |
| `demo/` | Runnable local demo |
| `eval/` | Faithfulness, citation coverage, unsafe-claim refusal fixtures |
| `CASE_STUDY.md` | Stub for Career Scout narrative |

## Status

Skeleton only — implementation in progress via Build Lab cloud agent.
