# Lab Notebook

Dated entries of what was run and what was learned.

---

## 2026-11-02: Drug annotation draft

**Ran:** `python data/build_drug_annotations.py` → `data/drug_annotations_draft.csv` (38 drugs).

**Result:**
- Structures (SMILES from PubChem): 38 / 38.
- Structure + mechanism (ChEMBL): 34 / 38.
- No ChEMBL mechanism: GELDANAMYCIN, L778123, MRK-003 (found, no mechanism record), MK-4541 (no confirmed ChEMBL record; PubChem CID 59691338 lists "MK-4541" as a synonym).

**What went wrong first and how it was fixed:**
1. First run: only 20 / 38 had mechanisms. Cause: mechanisms were looked up on the parent compound, but ChEMBL often stores them on the salt form. Fixed by filtering on `parent_molecule_chembl_id`.
2. Free-text search fallback matched MRK-003 to MRK-740 (wrong compound). Replaced it with PubChem's ChEMBL cross-reference. MRK-003 now maps to CHEMBL196215 via PubChem CID 15953832.
3. PD325901 maps to MIRDAMETINIB (CHEMBL507361). Confirmed: both ChEMBL and PubChem list PD-0325901 as a synonym.

**Still to do before this becomes `data/drug_annotations.csv`:**
- Find cited sources for the 4 drugs above, or mark them "unknown". Possibly ask the research team about the Merck compounds (plan Section 16).
- Fill `drug_class` (empty for all drugs right now).
- Hand-review all 34 "check" rows.
- Confirm drug name spellings against the actual O'Neil data once Ryan's pipeline loads it (plan Section 15).
