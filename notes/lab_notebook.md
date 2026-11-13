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

## 2026-11-09: PubMed retrieval working

**Built:** `agent/retrieval.py` (`search`, `evidence_for_drug`, `evidence_for_pair`, cache, exclusion filter), `agent/excluded_sources.txt`, `tests/test_retrieval.py` (8 offline tests with a fake PubMed).

**Checked by hand** on 3 well-known pairs and 2 Merck compounds:
- ABT-888 + carboplatin: veliparib PARP / synthetic-lethality papers; several veliparib + carboplatin trials for the pair.
- Lapatinib + erlotinib: HER2/EGFR review chapters and drug profiles; pair results are ErbB-family reviews.
- PD325901 + MK-2206: MEK and AKT inhibitor papers; pair results are MAPK + AKT co-inhibition studies.
- MK-4541 + doxorubicin: both MK-4541 SARM papers found; no paper on the pair (expected).
- MRK-003 + paclitaxel: 5 gamma-secretase / Notch papers; 2 papers on Notch inhibition with paclitaxel.
- A fully cached repeat takes about 0.4 s, with no network calls.

**Exclusion check:** a search designed to surface the O'Neil screen removed DeepTraSynergy (PMID 37467066) and a computational prediction platform (PMID 29483097), and kept the biology papers.

**Known limitations:** a few off-topic hits remain for famous drugs (e.g. erlotinib in Alzheimer's models). The critique step should discount weak sources; SHELDON should improve this later.

## 2026-11-09: LLM prompts built (live check pending)

**Built:** `agent/prompts.py` (hypothesize / critique / select, validation, one retry, fallback, per-call logging to `results/llm_logs/<run_id>.jsonl` with tokens and cost), `tests/test_prompts.py` (11 offline tests with a fake Claude), `experiments/try_prompts.py` (live smoke test on 3 real drug pairs with real retrieval).

**Status:** All 24 tests pass. The live smoke test could not run: `ANTHROPIC_API_KEY` in `.env` is the README placeholder, not a real key.

**Rough cost guess (unmeasured):** about 10–20k input tokens and 3–8k output tokens per call, so roughly $0.10–0.25 per call. At 3 calls × 25 rounds, that's about $8–19 per 250-experiment run. Measure from the smoke test and the first full run before planning seeds × ablations.

## 2026-11-09: Hypothesis tracking, explanations, and full LLM agent loop

**Built:** `agent/hypotheses.py` (HypothesisBook: add, critique verdicts, status updates, save), `agent/explanations.py`, `LLMChooser` in `agent/agent.py` (shortlist → retrieve → hypothesize → critique → select → explain), `--chooser llm` and `--outcome` flags, `tests/test_agent_llm.py`.

**Checked (offline, fake Claude):** a full 250-experiment run logs a hypothesis ID, a labeled explanation, and source IDs on every agent pick; hypothesis statuses change as results arrive; 72 LLM calls are logged (3 per round, rounds 1–24); no prompt mentions thresholds or strong flags. 30/30 tests pass.

**Run files:** `results/run_log_agent_seed<N>.csv` (LLM agent), `results/run_log_agent_random_seed<N>.csv` (skeleton), `results/hypotheses_<run_id>.json`, `results/llm_logs/<run_id>.jsonl`.

**Blocked:** the real-LLM run (`python -m agent.agent --chooser llm`) waits on a real `ANTHROPIC_API_KEY` in `.env`; `SimLab` is not in the repo yet.

## 2026-11-09: Backup lab built and first baseline comparison (real O'Neil data)

**Built:** `backup_lab/` (fetch_oneil, clean_oneil, sim_lab, response_model, baselines, thresholds, run_baselines, compare), `agent/lab_source.py` (the LAB_SOURCE switch), agent shortlist now uses the response model, `tests/test_backup_lab.py`. 42/42 tests pass.

**Data:** 92,208 raw O'Neil rows → 22,737 (pair, line) experiments: 583 pairs, 38 drugs, 39 lines, 6 tissues. 22,422 rows average 4 replicates, 315 average 8. 0 dropped. 16,907 visible to methods after holding out 10 lines.
Held-out: A2780, HT29, KPL1, LOVO, NCIH23, NCIH520, RPMI7951, SKMEL30, UWB1289+BRCA1, ZR751.
Strong cutoffs (top 5% / top 1%): synergy (ZIP) 11.84 / 19.00; inhibition (CSS) 81.89 / 90.59.

**Baselines, 5 seeds, strong combinations found in 250 experiments (mean ± std):**

| method | synergy top 5% | synergy top 1% | inhibition top 5% | inhibition top 1% |
|---|---|---|---|---|
| random | 12.2 ± 1.2 | 2.8 ± 0.7 | 12.8 ± 1.7 | 3.8 ± 0.7 |
| uncertainty | 27.4 ± 12.5 | 9.6 ± 9.1 | 10.4 ± 7.3 | 3.2 ± 3.3 |
| BO (UCB) | 65.2 ± 5.5 | 22.6 ± 3.6 | 112.0 ± 13.7 | 52.6 ± 11.5 |

Random matches chance (12.5 expected). BO is a strong bar: ~5× random for synergy, ~9× for inhibition. Figures: `results/backup/figures/`.

**Notes:** uncertainty sampling varies a lot by seed. Inhibition is much easier to find than synergy (it depends mostly on how potent each drug is in each line).

## 2026-11-13: Baselines under the team's definitions (Loewe + CSS, joint, within-line primary)

Strong combinations found in 250 experiments, 5 seeds, mean ± std. Chance ≈ 12.5. "bo:synergy" = BO optimizing synergy.

| method | within-line (primary), Loewe | all-experiments, Loewe | within-line, Bliss | all-experiments, Bliss |
|---|---|---|---|---|
| random | 10.6 ± 2.9 | 13.6 ± 3.2 | 13.0 ± 2.6 | 12.2 ± 1.7 |
| uncertainty:synergy | 6.6 ± 4.1 | 7.2 ± 1.8 | 14.0 ± 3.1 | 13.0 ± 9.7 |
| uncertainty:inhibition | 10.4 ± 5.6 | 15.8 ± 4.6 | 12.0 ± 4.7 | 19.0 ± 6.8 |
| bo:synergy | **35.4 ± 18.9** | 44.4 ± 19.6 | **33.4 ± 8.9** | 41.8 ± 12.5 |
| bo:inhibition | 22.2 ± 7.6 | 37.8 ± 15.4 | 23.2 ± 3.7 | 39.6 ± 17.7 |

**Takeaways:** BO (optimizing synergy) is ~3× random on the primary definition. Uncertainty sampling ≈ random. BO optimizing CSS loses ~40% under within-line ranking (66% of its picks are in the 5 most sensitive lines), which is the effect the within-line definition is meant to remove. Bliss gives the same conclusions. BO varies a lot by seed with Loewe (±19); consider 10 seeds.

**Not done this week:** real-LLM agent runs (`.env` key is still a placeholder), no-LLM control, DepMap features, response-model checks. Ryan's `lab/` is still empty, so the backup lab is the working lab.

## 2026-11-13: Everything without the API key (Isaias now owns all tasks)

**Built:** cell-line genetics from Cell Model Passports (`backup_lab/fetch_cell_lines.py`, `cell_line_map.py`, `cell_line_features.py`, `drug_target_genes.py`); genetics in the response model and in the agent's prompts; joint target (`agent/targets.py`); shared shortlist (`agent/shortlist.py`); `shortlist_random` control; ablations (`--ablation no_literature | no_critique | masked_names`); held-out prediction step (`predict_heldout`) and scorer (`backup_lab/mechanism_test.py`); famous vs obscure (`backup_lab/familiarity.py`); response-model check (`backup_lab/model_check.py`); `experiments/sanity_checks.py`; `experiments/estimate_cost.py`. 59 tests pass.

**Response model check** (`results/backup/model_check.csv`, tuning seeds): rank accuracy on unseen experiments 0.28 → 0.46 (synergy) and 0.41 → 0.59 (inhibition) as training grows 50 → 250. Uncertainty is calibrated (71–76% within 1 sd; 91–95% within 2 sd) and tracks error for synergy (0.23–0.35) but barely for inhibition (0.03–0.09), which explains why uncertainty sampling fails. Genetics add ≤ 0.02 here (the model already knows each line by name); they matter for reasoning about unseen lines.

**BO tuning** (seeds 100–104, `results/backup/tuning/`): kappa 0 → 41.4, 0.5 → 36.2, **1 → 43.6**, 2 → 30.4, 4 → 17.0 strong (primary). Keep kappa = 1.

**Final baselines** (seeds 0–4, target = joint, with genetics). Strong combinations found in 250 (mean ± sd; chance ≈ 12.5):

| method | primary (within-line joint) | secondary (all-experiments joint) | picks in 5 most sensitive lines |
|---|---|---|---|
| random | 10.6 ± 2.9 | 13.6 ± 3.2 | 18% |
| uncertainty | 15.4 ± 3.4 | 14.8 ± 4.0 | 16% |
| shortlist_random | 45.2 ± 13.4 | 38.6 ± 14.5 | 16% |
| **BO** | **47.2 ± 7.9** | **47.2 ± 14.5** | 22% |

**Key point:** picking at random from the model's 50-candidate shortlist nearly matches BO's top picks. The shortlist carries most of the value; the LLM must choose better than ~45–47 from that list to show it adds anything. Aiming at the joint target also cut BO's sensitive-line bias (22% of picks vs 66% when it optimized CSS alone).

**Famous vs obscure** (primary definition): obscure-only pairs are 11% of experiments but 14% of strong ones. BO (joint) finds 11.8 / 26.4 / 9.0 strong in famous / mixed / obscure pairs. Earlier synergy/inhibition-target logs in `results/backup/` predate genetics and kappa tuning; the joint-target logs are the reported ones.

**Cost estimate** (one full run, fake Claude, real prompts): 73 calls, ~650k input tokens. Opus 5.5 at high effort ≈ $5–11 per run, too expensive for the < $30 budget. Leaning toward Sonnet 5.5 with medium effort and trimmed literature (≈ $1.50–3.50 per run) for one demonstration run of each LLM arm; not switched yet.

**Sanity checks:** 75 run logs, 401 papers returned from cached searches (3 excluded papers in the raw cache, all filtered out), all pass.

**Still blocked on the API key:** steps 3–4 of the ladder (agent without / with literature), the other ablations, the mechanism test, reading explanations, real cost.
