# Decision Log

Every design decision, the alternatives considered, and why.

---

## 2026-11-02: How drug annotations match ChEMBL records

**Decision:** `data/build_drug_annotations.py` matches each drug to ChEMBL by (1) exact preferred name, (2) exact synonym, or (3) the ChEMBL ID that PubChem lists for the same compound. If none of these work, the drug is marked "not found in ChEMBL". There is no free-text search fallback.

**Alternatives:** Take the first free-text search result (the original draft).

**Why:** Free-text search matched MRK-003 to MRK-740, a different compound, and matched MK-4541 to an unnamed record we could not confirm. A wrong molecule would give the agent false mechanisms and Ryan's model a false structure. A missing value is safer than a wrong one.

## 2026-11-02: Look up mechanisms by parent compound

**Decision:** Query ChEMBL mechanisms with `parent_molecule_chembl_id` and store the parent ChEMBL ID in `chembl_id`.

**Alternatives:** Query by the exact molecule ID (the original draft).

**Why:** ChEMBL often files a mechanism under the approved salt form (for example, erlotinib's is on erlotinib hydrochloride). Querying the parent ID alone returned no mechanism for 14 well-known drugs, including erlotinib, doxorubicin, and gemcitabine.

## 2026-11-02: Drugs with no database mechanism stay "unknown"

**Decision:** GELDANAMYCIN, L778123, MK-4541, and MRK-003 have no ChEMBL mechanism record. Their mechanism fields stay blank (to be marked "unknown" in the reviewed file) until we find a cited source. We do not fill them from memory or from the LLM.

**Why:** Project rule: never guess biomedical facts. These are the obscure compounds that the famous-vs-obscure analysis (plan Section 9.4) depends on, so their sources matter.
