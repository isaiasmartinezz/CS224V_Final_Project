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

## 2026-11-09: PubMed retrieval design (`agent/retrieval.py`)

**Decision:**
- PubMed E-utilities (esearch + efetch), sorted by **relevance**. The API defaults to newest-first, which returned off-topic recent papers for well-studied drugs (e.g. erlotinib → a Chikungunya paper).
- Single-drug mechanism search requires the drug name in the **title**, then tops up from abstract matches when fewer than 5 are found. Title-only cut the Merck compounds (MK-4541, MRK-003) to 1 paper each.
- Drop papers with no abstract and repeated titles (the same review chapter appeared in 2010, 2014, and 2018 editions).
- Drug names are searched as both the dataset name and the common name from `data/drug_annotations.csv` (e.g. ABT-888 OR veliparib).
- Raw responses are cached in `data/cache/pubmed/` (gitignored; rebuildable). Exclusions are applied on every read, so editing the exclusion list never requires re-downloading.

**Why:** Relevant, reproducible, free evidence until SHELDON access arrives.

## 2026-11-09: Leakage exclusion list (`agent/excluded_sources.txt`)

**Decision:** Two layers.
1. Exact IDs: O'Neil 2016 (PMID 26983881, DOI 10.1158/1535-7163.MCT-15-0843, confirmed via PubMed).
2. Text patterns on title + abstract: mentions of O'Neil, the Merck screen, or DrugComb, and computational synergy-prediction papers (e.g. "drug synergy prediction", "deep learning ... synergy").

**Alternatives:** Hand-list every paper built on the O'Neil data. Not feasible: many ML papers use it, and their abstracts often don't name it (DeepSynergy says only "largest publicly available synergy dataset").

**Why:** The agent needs mechanism biology, not other models' predictions, so dropping the whole category costs little. Patterns are kept tight: a looser "synergy ... predict" rule removed a biology paper (PMID 37491889) where a gene was "predictive of" combination response.

## 2026-11-09: LLM model and call settings (`agent/prompts.py`)

**Decision:** All agent runs use **Claude Opus 5.5 (`claude-opus-5-5`)** with adaptive thinking at effort **`high`**, set once as constants in `agent/prompts.py`.

**Alternatives:** Sonnet 5.5 (half the price) or Opus 5.5 at the default `medium` effort. Either could be tested later as a cost ablation, but switching mid-project would make runs incomparable.

**Why:** The hypothesize and critique steps are reasoning-heavy, which is where higher effort pays off. One fixed model keeps runs comparable (plan Section 12).

**Refusal fallback:** Requests opt into the API's server-side fallback (`fallbacks: "default"`). If a safety classifier declines a request (cancer-drug content could occasionally trip the "bio" classifier), the API reruns it on Anthropic's recommended fallback model instead of stalling the run. This technically breaks "one model," so every call logs `model_served`; we report the fraction of fallback-served calls and can turn this off if the team prefers.

## 2026-11-09: Structured outputs plus checks in code

**Decision:** Each step uses structured outputs (a fixed JSON schema built from pydantic classes via `anthropic.transform_schema`). Code then checks what a schema can't express: cited IDs must be among the provided sources, drugs and cell lines must exist in the shortlist, mechanistic hypotheses must name predicted responders, critique gives one verdict per hypothesis, and select returns exactly k unique shortlist IDs. On failure: one retry with the problems listed, then hypothesize/critique return None and select falls back to the shortlist's top k (response-model order).

**Why:** Catches invented citations and invalid picks before they reach the lab, and a run never stalls on a bad LLM answer.

## 2026-11-09: Hypothesis status rule (`agent/hypotheses.py`)

**Decision:** After each batch, every active hypothesis is re-scored using only results the lab has returned. Each observed experiment gets its percentile rank among all experiments run so far, and a hypothesis's score is the mean percentile of the experiments it covers (one-drug hypothesis: any pair with that drug; multi-drug: both drugs in its set). Status: fewer than 2 covered experiments → open; score ≥ 0.65 → supported; ≤ 0.35 → refuted; otherwise open. Mechanistic hypotheses also record `responder_gap` (predicted responder lines vs other lines), which feeds the held-out mechanism test later.

**Alternatives:** Compare against the top-5% "strong" threshold. Rejected: the threshold comes from hidden results (leakage, plan Section 13).

**Why:** Simple, transparent, and leak-free. The cutoffs (2 tests, 0.65 / 0.35) are untuned starting values to revisit after the first real runs.

## 2026-11-09: Explanations downgrade unsupported "mechanistic" labels

**Decision:** A pick labeled mechanistic whose hypothesis names no predicted responder lines, or an "explore" pick, is logged as statistical.

**Why:** Plan Section 8.3 requires every mechanistic explanation to carry a testable cell-line prediction; this enforces it in code rather than trusting the label.

## 2026-11-09: Random shortlist until the response model exists

**Decision:** `LLMChooser.shortlist` samples 50 candidates at random for now; literature is retrieved for the first 6 drug pairs on the shortlist (3 papers per query) to keep prompts affordable.

**Why:** The milestone allows a random shortlist until Ryan's response model is ready. Note for analysis: with a random shortlist, any gain over the random baseline comes from the LLM alone.

## 2026-11-09: Backup copy of Ryan's tasks, behind an on/off switch

**Decision:** Isaias built working versions of Ryan's Week 1–2 tasks (data pipeline, held-out lines, SimLab, response model, baselines, thresholds, comparison plots) in a separate `backup_lab/` package with its data in `data/processed/backup/`. Nothing in Ryan's `lab/` or `data/processed/` is touched. `LAB_SOURCE` (in `.env`, or `--lab` per run) picks whose version every runner uses: `backup` (default), `ryan`, or `stub`. Results go to `results/<source>/` so the two versions never mix. Turning the backup off = `LAB_SOURCE=ryan`.

**Why:** Unblocks the agent's first real runs without waiting, while keeping Ryan's work authoritative once it lands. Compare the two versions before switching (same row count, same held-out lines, same thresholds).

## 2026-11-09: Data source = DrugComb v1.5 via Zenodo

**Decision:** O'Neil rows (study_name ONEIL) are streamed from DrugComb v1.5 `summary_v_1_5.csv` on Zenodo (record 15235991); drugcomb.org refused connections on Nov 9. Inhibition = `css_ri` (checked: equals the mean of `css_row` and `css_col` for every row). All four synergy scores are kept; `synergy` = ZIP for now.

**Name matching:** each DrugComb drug name was looked up in PubChem and its CID compared with `data/drug_annotations.csv`. 36/38 match exactly; carboplatin and oxaliplatin map to a different PubChem record of the same compound (same formula, common name in PubChem synonyms). Mapping and evidence in `backup_lab/clean_oneil.py`.

**Open:** ZIP is provisional until the research team answers the synergy-score question (plan Section 14). Switch with `SYNERGY_METRIC=loewe|bliss|hsa` in `.env`; no rerun of cleaning needed.

## 2026-11-09: Held-out lines (backup version)

**Decision:** 10 of 39 lines, chosen once with seed 2026, spread across tissues by largest remainder: 2 each from breast, large intestine, lung, ovary, skin; 0 from prostate (only 2 lines). List committed at `data/processed/backup/heldout_lines.txt`. If Ryan's list differs, his wins when `LAB_SOURCE=ryan`.

## 2026-11-09: Response model and baselines (backup version)

**Decision:** Random forest (100 trees, max_features 0.3), retrained from scratch each round. Features: summed Morgan fingerprints of both drugs (radius 2, 256 bits, RDKit), summed ChEMBL target multi-hot, summed drug identity, cell line one-hot, tissue one-hot. Uncertainty = std across trees. Uncertainty sampling = top-k std; BO = top-k of mean + 1.0 × std (UCB, no batch diversity). The agent's shortlist uses the same model: 45 by UCB + 5 most uncertain, ordered by UCB, with pred_mean / pred_std / tissue shown to the LLM.

**Why:** Simple, fast (~8 s per 250-experiment run), and gives honest uncertainty. kappa = 1.0 is untuned. DepMap genetics are not in the model yet.

**Interface assumed for Ryan's model** (used when LAB_SOURCE=ryan): `ResponseModel(cell_lines, seed=)` with `fit(history, outcome)` and `predict(candidates) -> (mean, std)`. See `notes/interface.md`.

## 2026-11-13: Outcome scores, per research-team feedback (Janina, Minseung)

**Decision:** Synergy = **Loewe** (comparable with prior ML work on this dataset, starting with DeepSynergy). **Bliss** = robustness check (the original O'Neil scoring). Inhibition = **CSS** from DrugComb. Supersedes the provisional ZIP choice of 2026-11-09. Bliss runs go to `results/backup_bliss/` (`SYNERGY_METRIC=bliss`).

## 2026-11-13: "Strong" = joint cutoff, ranked within each cell line (primary)

**Decision:** A combination is strong if it passes a cutoff on *both* scores: top 10% Loewe and a CSS cutoff tuned so ~5% of non-held-out experiments qualify (CSS lands at about the top 31%). **Primary:** both scores ranked within each cell line (`joint_within_line`). **Secondary:** the same rule ranked over all experiments (`joint`). Single-score top 5% / 1% kept as extra checks. Code: `backup_lab/thresholds.py`; `backup_lab/compare.py` defaults to the primary.

**Alternatives:** sum of the two scores (rejected: different scales, team advice); all-experiments ranking as primary (rejected: see below).

**Why:** Without within-line ranking a method can score well by finding generally drug-sensitive lines. Measured: with CSS alone 5 of 29 lines hold 57% of strong combinations (MSTO has 181, two lines have none); the all-experiments joint rule still gives 39%; within-line gives 21% (an even spread is 17%). BO optimizing CSS puts 66% of its picks in the 5 most sensitive lines (random: 18%).

## 2026-11-13: Agent is built on top of the statistical model

**Decision:** The response model shortlists 50 candidates (BO score plus a few most-uncertain); the LLM chooses 10 from that list using literature. Headline comparison: agent vs BO on its own. The **no-LLM control** (model picks from its own top 50, no LLM) is therefore the main control and runs alongside the first real agent runs, not in Week 4.

**Why:** It's how the agent is designed, and it isolates what the literature reasoning adds beyond statistics.

**Still open:** whether baselines should optimize the joint goal directly (they currently optimize one score: synergy or inhibition).
