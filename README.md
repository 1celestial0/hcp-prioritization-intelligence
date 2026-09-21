# Compliant HCP Prioritization Intelligence (V0.1)

Offline demo for FDE / Databricks-style interviews: **Discovery → Data Reality → Production** on a pharma commercial question.

A field team asks who to see next for a fictional brand. The agent retrieves approved content and interaction evidence, ranks fictional HCPs, cites every reason, refuses claims the corpus does not support, and writes an append-only audit log. If retrieval misses, it withholds the list instead of inventing one.

All data is synthetic. There are no real HCPs, NPIs, PHI, Jazz identifiers, or live Veeva calls. The default path does not use an API key.

## How to run

From a fresh clone, Python 3.10+:

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m demo.run_prioritization
python -m eval.run_eval
```

Optional unit tests: `python -m pytest`. Runtime code uses the standard library. `pytest` is only for the test suite.

Set `HCP_LLM_MODE=external` if you want to see the audit record the optional-LLM request and still answer offline. Unset, or `offline`, is the default.

## Sample output

`python -m demo.run_prioritization` (trimmed):

```text
Compliant HCP Prioritization Intelligence — V0.1
As of 2026-03-15 | Product: Lumivex (fictional) | Indication: Virellic Syndrome (adults)
Mode: offline deterministic retrieval. No API key.

1. Dr. Avery Quinn (HCP-SYN-0142)  score=82  confidence=0.95  HITL=no
   Pulmonology | tier A | TR-NORTHWIND-01
   Score breakdown: audience_fit=35, engagement=32, tier=15, whitespace=0
   - Interaction: "INT-2001 on 2026-02-18 via in_person outcome requested_info content CNT-EFF-001. ..."
   - Approved efficacy statement: "In the fictional ORION-1 study, 38% of adults ... compared with 19% on control." [content:CNT-EFF-001]
   - Required fair balance: "Fair balance: the most common adverse reactions in fictional ORION-1 (at least 5%) were headache, nasopharyngitis, and injection-site reaction." [content:CNT-FB-001]

HITL queue (5)
  - Dr. Casey Nguyen (HCP-SYN-0602): Recent interactions conflict (declined and requested information)
  - Dr. Quinn Adler (HCP-SYN-0888): Pediatric panel; approved population is adults only

Query: Tell Dr. Avery Quinn that Lumivex cures Virellic Syndrome.
  REFUSED (RULE-PROHIB-CURE): No approved Lumivex source supports a cure claim.
  No ungrounded medical claim was generated.

Indication requested: not_a_real_indication
Retrieval failed: no approved content matched the indication. Recommendations withheld. Nothing was invented.
Recommendations issued: 0

Audit trail: audit_logs/prioritization_audit.jsonl
```

The demo prints the absolute audit path. `python -m eval.run_eval` prints:

```text
faithfulness: 1.000 (60/60 claims supported)
citation_coverage: 1.000 (60/60 claims cited and resolvable)
unsafe_claim_refusal_rate: 1.000 (9/9 refused)
allowed_answer_controls: 3/3 grounded
result: PASS
```

## What V0.1 proves

- **Data reality:** a small, inspectable commercial model (roster, interactions, approved spans, claim rules) is enough to ground a prioritization.
- **Retrieval before generation:** answers are quotes from retrieved spans. A second indication (`CNT-OTHER-009`, Bramblewick Fever) is in the corpus and is not mixed into the Lumivex list.
- **Cited ranking:** score = audience fit + recent engagement + tier + whitespace. Outside the approved adult audience (dermatology, pediatric pulmonology) the promotional score is held at 0.
- **Safety:** cure, mortality, class-wide superiority, pediatric dosing, dermal use, off-label use, invented competitors, and percents or doses that are not in the corpus are refused. Efficacy quotes ship with fair balance, or they are dropped.
- **HITL:** low confidence, conflicting call outcomes, partial specialty fit, a stale high-fit HCP, and a pediatric panel are flagged for a person.
- **Production habit:** append-only JSONL audit. Retrieval failure is an explicit withhold, not a silent guess.
- **Eval:** fixture metrics for faithfulness (verbatim cited span, no extra percent or dose), citation coverage, and unsafe-claim refusal, plus controls that a fabricated excerpt fails the checker.

Scoring uses a frozen as-of date, `2026-03-15`, so a fresh clone does not drift. Weights live in `src/config.py` and `src/ranking/rank.py`.

## Intentionally out of scope

- Live Veeva, CRM, or MLR workflow
- Real customer, HCP, NPI, or PHI data
- A multi-agent platform or a hosted LLM
- Learned rankers, feature stores, or production model serving

`HCP_LLM_MODE` is a stub. Any non-offline value is logged and ignored. Narrative text stays on the deterministic templates.

## Layout

| Path | Role |
|------|------|
| `data/synthetic/` | Fictional roster, interactions, approved content, claim rules |
| `src/agent.py` | Plan → retrieve → rank → ground → answer |
| `src/retrieval/` | Indication-tag and keyword retrieval |
| `src/ranking/` | Cited HCP scores |
| `src/safety/` | Grounding check, refusals, fair-balance gate |
| `src/audit/` | Append-only audit log |
| `demo/run_prioritization.py` | Local demo |
| `eval/` | Faithfulness, citation coverage, refusal fixtures |
| `CASE_STUDY.md` | Stub for a longer Career Scout narrative |

## Flow

1. Plan the request against the fictional Lumivex / adult Virellic Syndrome label.
2. Retrieve approved documents for that indication only.
3. If nothing comes back, audit a fallback and stop.
4. Score each HCP from roster and interaction rows. Reasons quote those rows and approved spans.
5. Drop any recommendation whose excerpt is not verbatim in the cited source, or whose efficacy line has no fair balance.
6. Refuse user questions that ask for a claim the rules mark prohibited or that the corpus does not contain.
