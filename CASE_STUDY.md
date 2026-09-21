# Compliant HCP Prioritization Under Fair-Balance Constraints

**Portfolio artifact:** Phase 1 FDE evidence — Discovery → Data Reality → Production  
**Audience:** Forward Deployed / Applied AI hiring managers (Databricks primary)  
**Repo:** https://github.com/1celestial0/hcp-prioritization-intelligence  
**Data policy:** Synthetic identifiers only. No real HCP, PHI, client, or commercial proprietary data.

---

## 1. Business outcome

**Ambiguous ask:** “Which HCPs should the field prioritize this week, and what scientific exchange is safe?”

**Measurable outcomes for this thin slice:**
- Time to a *safe* priority list (ranked HCP + cited approved content)
- % of recommendations with at least one grounded citation
- Unsafe-claim refusal rate (recommendation blocked when grounding fails)
- Human-in-the-loop (HITL) rate on low-confidence or missing-evidence cases

“Safe enough to act” means: every substantive claim is tied to an approved content snippet, indication/fair-balance rules are checked, and gaps are escalated to a human — never filled with free-form medical language.

---

## 2. Data reality (synthetic fixtures)

Fixtures live under `data/synthetic/`:
- HCP roster (synthetic IDs, specialty, geography proxies)
- Interaction history (calls, emails, meetings — fictional)
- Approved content corpus (labeled snippets with indication tags)
- Fair-balance / indication rules (simple deterministic gates)

**What we treat as “real” constraints even on fake data:**
- Alias / HCO ambiguity (same person, multiple org affiliations)
- Sparse interaction history for many HCPs
- Content that is approved for one indication but not another
- Missing retrieval → no recommendation, not a creative completion

Career narrative only (not in this dataset): Modeyso-style HCP/HCO alias governance and MedPro-like universe thinking inform *what* we stress in fixtures. Employer, client, title, and tenure are intentionally omitted until Sourav confirms them separately.

---

## 3. Architecture choices (and what we refused)

**Flow:** retrieve → ground → rank → cite → safety gate → audit  
See `src/retrieval/`, `src/ranking/`, `src/safety/`, `src/audit/`.

| Choice | Why |
|--------|-----|
| Grounded retrieval over approved corpus | Field action needs citations, not chat fluency |
| Deterministic fair-balance / indication gates | Compliance rules should not be “vibes from the model” |
| HITL on low confidence | Regulated domains default to human review under uncertainty |
| Audit log + retrieval-failure fallback | Production ownership: explain what happened when evidence is missing |

**Refused for V0.1:**
- Free-form generation of medical claims
- Live Veeva / real CRM pulls
- Full MLR workflow automation
- Multi-agent platform sprawl before a working thin slice

Demo entrypoint (target): `demo/run_prioritization.py`

---

## 4. Evaluation design

Harness (target): `eval/run_eval.py` + `eval/fixtures/`

| Metric | Intent |
|--------|--------|
| Faithfulness | Output claims are supported by retrieved snippets |
| Citation coverage | Ranked recommendations carry usable citations |
| Unsafe-claim refusal | Ungrounded medical language is blocked |
| HITL trigger rate | Low-confidence / sparse-evidence cases escalate |

Numbers will be filled when V0.1 eval lands. Until then this section documents *what success means*, not marketing scores.

---

## 5. Production and audit posture

Even as a local demo, the thin slice is meant to show production thinking:
- Every ranking decision can be traced to retrieved evidence + rule checks (`src/audit/`)
- Retrieval failure → explicit fallback path, not a hallucinated priority list
- Monitoring hooks for drift later (content corpus changes, rule updates)

This is the difference between a portfolio chatbot and an FDE-shaped artifact.

---

## 6. What I would validate first with a real customer

1. Who is accountable for “safe enough to act” — medical, legal, or commercial ops?
2. What is the authoritative approved-content store and how often does it change?
3. How are HCP identity and HCO affiliation resolved today (aliases, merges, exclusions)?
4. What is the cost of a false positive (wrong priority) vs false negative (missed priority)?
5. Where must a human sign off before field action?

---

## 7. How to run (when V0.1 is ready)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m demo.run_prioritization
python -m eval.run_eval
```

See `README.md` for layout and status.

---

## Positioning note (interview 60 seconds)

I build the thin end-to-end loop: diagnose the real prioritization problem, confront messy HCP/content reality, ship the smallest grounded system that survives audit and human review, and measure refusal/citation quality — not just demo fluency. That is the FDE job in regulated commercial domains.
