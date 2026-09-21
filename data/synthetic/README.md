# Synthetic commercial dataset

Fictional portfolio data for the offline demo. Nothing here is a real HCP, NPI, product, study, or company.

| File | Contents |
|------|----------|
| `hcp_roster.csv` | 12 fictional HCPs: specialty, tier, territory, practice setting, panel focus |
| `interactions.csv` | Field interactions tied to synthetic content ids (or blank when no content was used) |
| `approved_content.json` | Approved snippets with indication tags and citable spans |
| `claim_rules.json` | Allowed claims, fair-balance requirement, prohibited patterns |

IDs use prefixes `HCP-SYN-`, `INT-`, `CNT-`, `RULE-`, and `TR-`. The loader rejects 10-digit values that look like NPIs.

Product in this slice: **Lumivex** (HelioSynth Therapeutics) for adults with fictional **Virellic Syndrome**. A separate document (`CNT-OTHER-009`, Bramblewick Fever) exists so retrieval must not mix indications.

Ranking as-of date is frozen at **2026-03-15** in `src/config.py`.
