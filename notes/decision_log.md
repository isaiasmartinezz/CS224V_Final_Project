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

## 2026-11-02: Agent skeleton runs against a stand-in lab

**Decision:** Until Ryan's `lab/sim_lab.py` and cleaned data exist, the agent runs against `agent/stub_lab.py`: the same methods and rules as `notes/interface.md`, the 38 real drug names, 39 fake cell lines (10 held out), and random scores. It lives in `agent/`, not `lab/`, so Ryan's folder is untouched.

**Why:** Week 1 goal is a full 250-experiment loop end to end; the plan allows a random-score stand-in. Delete it once SimLab lands.

## 2026-11-02: Strong-combination flags are added after the run, outside the agent

**Decision:** `run_agent` logs only what `lab.run()` returns. `agent/agent.py` main() adds `is_strong_synergy` / `is_strong_inhibition` (top 5%) after the run finishes.

**Why:** The thresholds come from all hidden results. Computing them inside the agent loop would leak information (plan Section 13). Needs agreement with Ryan on how SimLab exposes ground truth for evaluation only.

## 2026-11-02: Shared first batch via `agent.agent.initial_batch(candidates, seed, k)`

**Decision:** Round 0 is chosen by `initial_batch` from its own random stream seeded by `seed`, independent of the chooser. Ryan's baselines should call the same function.

**Why:** Plan Section 6 requires every method to start from the same random first batch per seed.

## 2026-11-02: Finishing drug annotations (`data/finalize_drug_annotations.py`)

**Decision:** Hand-written fields live in `data/finalize_drug_annotations.py`, which turns the draft into `data/drug_annotations.csv`.
- `drug_class` restates a sourced field in plain words: the WHO ATC group (names fetched from ChEMBL's `atc_class` endpoint), the ChEMBL mechanism, or a cited paper. The source is written in `notes` for every row.
- The 4 drugs with no ChEMBL mechanism get targets and mechanism from PubMed abstracts that name the drug, cited by PMID: GELDANAMYCIN (Hsp90), L778123 (FTase/GGTase-I), MK-4541 (SARM), MRK-003 (gamma-secretase / Notch). O'Neil 2016 was not used as a source.
- Blank fields become "unknown"; a missing ATC code becomes "none" (the drug isn't WHO-classified, which is a fact, not a gap).
- `status` is "needs sign-off" until Isaias reads each row and sets it to "done".

**Why:** Keeps every manual choice visible, sourced, and re-runnable, and follows the "never guess" rule.
