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

## 2026-11-02: Agent skeleton runs end to end

**Built:** `agent/agent.py` (loop + random chooser), `agent/stub_lab.py` (temporary fake lab), `tests/test_agent_skeleton.py`.

**Ran:** `python -m agent.agent --seeds 0 1 2 3 4` (about 2 seconds total).
- Every seed: 250 experiments, 25 rounds of 10, budget reaches 0.
- Strong finds (stand-in data, random chooser): synergy 11/15/13/13/15, inhibition 14/12/6/10/18. Chance level is 5% × 250 = 12.5, so this matches.
- Tests pass: no repeated experiments, no overspending, no held-out lines, same first batch across choosers.
- Run logs in `results/` are NOT committed: they come from fake scores.

**Next:** swap in Ryan's SimLab when ready; add an LLM chooser in the same slot as `random_chooser`; add PubMed retrieval with on-disk caching.

## 2026-11-02: Drug annotations finalized (pending sign-off)

**Ran:** `python data/finalize_drug_annotations.py` → `data/drug_annotations.csv` (38 rows, 13 columns).
- All 38 drugs have SMILES, mechanism, targets, and `drug_class`, each with a source in `notes`.
- Remaining unknowns: MK-4541 `chembl_id` (no confirmed ChEMBL record) and the `chembl_name` for MK-4541 and MRK-003 (ChEMBL records have no preferred name).
- Still open: confirm drug spellings against Ryan's `oneil_clean.csv`; Isaias to read each row and set status to "done".
