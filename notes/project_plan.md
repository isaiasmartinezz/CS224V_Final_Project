# Cancer-Combo-Agent: Project Plan

The single source of truth for this project. Read this before doing any work.
Last updated: Nov 2, 2026.

---

## 1. The project in one paragraph

Cancers that become resistant to one drug are often treated with drug combinations, but there are far too many possible pairs to test. Labs choose experiments by intuition; standard active-learning methods choose from numbers alone and ignore what is known about how drugs work. We test whether an agent that reasons like a scientist (proposing hypotheses from the literature, running a few experiments, and updating) finds strong drug combinations in fewer experiments than standard methods. We also test whether the mechanisms the agent proposes make correct predictions about which cancer cells will respond.

## 2. Research questions

1. **Discovery efficiency:** With the same budget of 250 experiments, does the agent find more strong combinations than random selection, uncertainty sampling, and Bayesian optimization?
2. **Mechanism validity:** When the agent proposes a mechanistic explanation, do the predictions it implies hold on cell lines it never saw?
3. **What drives any gain (ablations):** Is it the literature, the LLM's prior knowledge of famous drugs, or the statistical model?

## 3. Team, roles, and cadence

| Person | Role |
|---|---|
| Isaias Martinez | Agent, literature retrieval, drug annotations, explanations, leakage controls |
| Ryan Tan | Data pipeline, simulated lab, response model, baselines, evaluation plots |
| Dr. Bryant Lin, MD | Research advisor |
| Minseung Choi, Janina Troper | Research team advisors |
| Jeongyeon Kim | CS 224V TA mentor |
| Harshit Joshi | SHELDON contact (access requested) |

**Weekly cadence**
- Friday: TA meeting
- Monday 11:00: Isaias and Ryan sync
- Monday 12:00: research team meeting
- Monday noon: weekly progress update due

**Ownership rule:** each person owns their folders (see Section 10). Change someone else's code only after telling them.

## 4. Timeline

| Week | Dates | Goal | Done when |
|---|---|---|---|
| 1 | Oct 26 to Nov 1 (spilling into Nov 2) | Everything runs end to end, even if basic | Random-baseline discovery curve exists; agent completes a full 250-experiment run against the lab |
| 2 | Nov 2 to Nov 8 | Real components | Response model with uncertainty; uncertainty sampling and BO baselines; agent uses real literature retrieval |
| 3 | Nov 9 to Nov 15 | First real comparison | Agent vs all three baselines on both outcomes, multiple seeds. **Review with team Nov 16:** continue or adjust |
| 4 | Nov 16 to Nov 22 | Stress tests | Ablations, famous vs obscure analysis, held-out mechanism test. **Code freeze Nov 22** |
| 5 | Nov 23 to Nov 29 | Final runs | Final numbers and figures; paper draft |
| 6 | Nov 30 to Dec 2 | Present | **Dry run Nov 30; final presentation Dec 2** |

Detailed per-person task checklists for every week are in `notes/milestones.md`.

## 5. Data

### Primary dataset: O'Neil et al. 2016
Merck combination screen. Approximate figures (VERIFY when loading and record exact numbers in Section 15):
- ~38 drugs, ~39 cancer cell lines (breast, colon, lung, ovarian, melanoma, prostate, others)
- ~22,000 (drug pair, cell line) experiments, each with dose-response measurements
- About half the drugs are Merck research compounds (MK-xxxx codes), which are less studied. This helps leakage control.

### Where to get it
- **DrugComb portal**: harmonized screens with synergy scores (ZIP, Loewe, Bliss, HSA) and a sensitivity score (CSS). Filter to the O'Neil study.
- **Therapeutics Data Commons (TDC)**: Python loaders for drug-synergy datasets. Check which TDC dataset corresponds to O'Neil and whether it includes drug names (some versions only give structures).
- Save raw downloads in `data/raw/` (not committed). Save cleaned data in `data/processed/`.

### Cleaned table: `data/processed/oneil_clean.csv`
One row per (drug pair, cell line):

| column | meaning |
|---|---|
| exp_id | unique ID |
| drug_a, drug_b | drug names, sorted alphabetically so each pair appears once |
| cell_line | cell line name |
| tissue | tumor type |
| synergy | synergy score (metric TBD, see Section 14) |
| inhibition | growth inhibition score (CSS) |

Cleaning rules:
- Average replicate measurements for the same (pair, cell line); record how many replicates were averaged.
- Treat (A, B) and (B, A) as the same pair.
- Drop rows missing either outcome; record how many were dropped.

### Held-out cell lines: `data/processed/heldout_lines.txt`
- About 25% of cell lines (~10), chosen randomly with a fixed seed, spread across tissues where possible.
- These are excluded from the agent's candidates and only used for the mechanism test (Section 9.3).
- Choose once, commit the file, never change it.

### Drug annotations: `data/drug_annotations.csv`
One row per drug: drug, search_name, pubchem_cid, smiles, chembl_id, chembl_name, targets, mechanism, action_type, atc_codes, drug_class, status, notes.
- Built by `data/build_drug_annotations.py` (PubChem for structures, ChEMBL for targets and mechanisms), then reviewed by hand.
- Drug names must match the dataset spelling exactly.
- Unknowns are marked "unknown". Never guessed.

### Cell line features (week 2)
- Match cell lines to DepMap for genetics (mutations, expression of key genes). The agent uses these to reason about mechanisms (for example, "this line has a BRCA mutation").

## 6. Definitions

- **Budget:** 250 experiments per method per run.
- **Batch size:** 10 experiments per round (25 rounds).
- **Strong combination:** top 5% of all non-held-out experiments, computed separately for synergy and for inhibition. Top 1% as a sensitivity check.
- **Seeds:** every method runs with at least 5 random seeds; report mean and spread.
- **Initial batch:** every method starts from the same random first batch per seed, so comparisons are fair.

## 7. The simulated lab (Ryan): `lab/sim_lab.py`

See `notes/interface.md` for the exact contract.
- `SimLab(data_path, heldout_path, budget=250, outcome=...)`
- `candidates()`: table of exp_id, drug_a, drug_b, cell_line for all non-held-out experiments not yet run
- `run(exp_ids)`: returns exp_id, synergy, inhibition; each ID counts once against the budget; repeats and overspending raise errors
- `budget_remaining()`
- Logs every call so runs can be replayed.

## 8. Methods compared

### 8.1 Response model (Ryan, week 2)
Predicts a score for any untested experiment, with an uncertainty estimate.
- Features: drug structure fingerprints (Morgan fingerprints from SMILES via RDKit), drug targets, cell line features (DepMap), tissue.
- Model options: an ensemble (random forest or several small neural nets) where disagreement gives uncertainty, or a Gaussian process. Start simple.
- Retrained after every batch on all results seen so far.

### 8.2 Baselines (Ryan)
1. **Random:** pick 10 untested experiments at random each round.
2. **Uncertainty sampling:** pick the 10 the model is least sure about.
3. **Bayesian optimization:** pick the 10 with the best balance of high predicted score and high uncertainty (upper confidence bound or expected improvement).

### 8.3 The agent (Isaias): `agent/`
Statistical tools estimate responses; the LLM never predicts scores itself.

Each round:
1. **Shortlist:** the response model scores all candidates; keep the top ~50 by the BO criterion, plus a few high-uncertainty ones.
2. **Retrieve evidence:** for each shortlisted drug pair, retrieve literature on both drugs' mechanisms and any known interaction (SHELDON, or PubMed as a placeholder). Use drug annotations and cell line features.
3. **Hypothesize:** the LLM proposes hypotheses, for example "PARP inhibitor plus DNA-damaging agent should be synergistic in DNA-repair-deficient lines."
4. **Critique:** a second LLM pass challenges each hypothesis against the evidence and results seen so far.
5. **Select:** choose the batch of 10, balancing promising hypotheses with tests that would distinguish between competing ones.
6. **Run and update:** send the batch to the lab, record results, mark hypotheses supported or refuted, and carry them into the next round.

Every flagged combination gets an **explanation** labeled by level:
- **Mechanistic:** a specific pathway in these cells. Must include a testable prediction: which cell lines should respond, and why.
- **Cross-cancer:** worked in other tumor types.
- **Statistical:** similar drugs behaved this way.

Week 1 version: a skeleton that runs the loop end to end (random or simple LLM choice) against the lab or a random-score stand-in.

### 8.4 Literature retrieval
- **Target:** SHELDON (access requested from Harshit Joshi).
- **Placeholder:** PubMed E-utilities (free, no key needed for light use; add an NCBI API key for higher rate limits).
- Cache every retrieval result to disk so runs are reproducible and cheap to repeat.

## 9. Evaluation

### 9.1 Discovery efficiency
- **Discovery curve:** x = experiments run (0 to 250), y = strong combinations found. One curve per method, mean plus spread across seeds.
- **Headline numbers:** strong combinations found at 250; area under the discovery curve; experiments needed to find the first N strong combinations.
- Report synergy and inhibition separately.

### 9.2 Ablations (week 4)
| Variant | What it tests |
|---|---|
| Agent without literature | Does retrieved evidence help? |
| Agent with masked drug names ("Drug 17") | Is the LLM just recalling known results? |
| Agent without critique step | Does self-critique help? |
| Model-only shortlist (no LLM selection) | Equals BO; isolates the LLM's contribution |

### 9.3 Mechanism test (held-out cell lines)
- For each mechanistic explanation, the agent predicts which held-out lines should respond.
- Score those predictions against the actual held-out results: how often predicted responders really respond, compared to a baseline of picking lines at random.
- Only ~10 held-out lines, so treat this as exploratory and report it honestly.

### 9.4 Famous vs obscure
- Split drug pairs into well-studied (approved drugs with many papers) and obscure (Merck research compounds).
- If the agent only beats baselines on famous pairs, its gain may come from memorization, not reasoning.

## 10. Repository layout

```
CS224V_Final_Project/
  CLAUDE.md                  context for Claude Code
  README.md                  setup instructions
  requirements.txt
  .env                       API keys (never committed)
  data/
    raw/                     downloads (not committed)
    processed/               cleaned data (not committed except heldout_lines.txt)
    drug_names.txt           Isaias
    build_drug_annotations.py  Isaias
    drug_annotations.csv     Isaias
  lab/                       Ryan: sim_lab.py, response_model.py, baselines.py
  agent/                     Isaias: agent.py, retrieval.py, prompts.py, explanations.py
  experiments/               scripts that run full comparisons
  results/                   run logs, figures
  notes/
    project_plan.md          this file
    interface.md             lab <-> agent contract
    decision_log.md          every design decision and why
    lab_notebook.md          dated entries of what was done and learned
    weekly_updates/          one file per Monday update
```

## 11. Logging (both)

Every run writes `results/run_log_<method>_seed<N>.csv` with one row per experiment:
round, exp_id, drug_a, drug_b, cell_line, synergy, inhibition, is_strong_synergy, is_strong_inhibition, and for the agent: hypothesis_id, explanation_level, explanation_text, retrieved_source_ids.

LLM calls are logged separately (prompt, response, model, tokens, cost) in `results/llm_logs/`.

## 12. Environment

- Python 3.11 in `.venv` (`python3.11 -m venv .venv`, `source .venv/bin/activate`, `pip install -r requirements.txt`).
- Run `conda deactivate` first if Anaconda is active.
- Packages to add as needed: `rdkit` (fingerprints), `torch` and `botorch` or scikit-learn (models), `PyTDC` (data loading).
- API keys in `.env`: `ANTHROPIC_API_KEY`, optionally `NCBI_API_KEY`.
- Use one fixed LLM model for all agent runs and record it in the decision log.

## 13. Leakage controls

The agent must not see the answers.
- Never pass hidden results or the dataset file to the agent; it only sees what `lab.run()` returns.
- Exclude O'Neil et al. 2016 and any paper reporting its screen results from retrieval (filter by title, authors, and DOI; keep the exclusion list in `agent/excluded_sources.txt`).
- Run the masked-drug-name ablation (Section 9.2).
- Report famous vs obscure results separately (Section 9.4).

## 14. Open questions

| # | Question | Ask | Status |
|---|---|---|---|
| 1 | SHELDON access; can it exclude specific papers? | Harshit Joshi | Emailed, waiting |
| 2 | How does DataSTORM relate to this project? | Research team | Open |
| 3 | Is O'Neil alone enough, with NCI-ALMANAC as a stretch? | Research team | Open |
| 4 | Which synergy score: ZIP, Loewe, or Bliss? | Research team | Open |
| 5 | What counts as success by Dec 2? | Research team | Open |
| 6 | Course LLM credits? | TA | Open |
| 7 | Can Isaias publish a write-up on his website? Attribution? | Dr. Lin, TA | Open |

Update the Status column as answers arrive and record decisions in `notes/decision_log.md`.

## 15. Facts to verify and record

- Exact counts: drugs, cell lines, experiments, replicates
- Exact drug name spellings in the dataset
- Which held-out lines were chosen (and the seed)
- Score distributions and the top-5% thresholds for each outcome
- Author names and years for all references before they go in the paper

## 16. Risks and fallbacks

| Risk | Fallback |
|---|---|
| SHELDON access is slow | PubMed placeholder; swap in later |
| Agent doesn't beat BO | Still publishable: report where it helps (obscure pairs? early rounds?) and where it doesn't |
| LLM costs too high | Cache retrievals; shorten shortlist; use a cheaper model for critique |
| Merck compounds lack annotations | Mark unknown; ask the research team; analyze them as a separate group |
| Held-out test too small | Report as exploratory; consider NCI-ALMANAC for more lines |
| Falling behind | Week 3 review (Nov 16) is the decision point to cut scope |

## 17. Weekly update template

Save each as `notes/weekly_updates/YYYY-MM-DD.md`:
1. What we planned this week
2. What we finished (Isaias / Ryan)
3. Results so far (with a figure if we have one)
4. What's blocked and what we need
5. Plan for next week

## 18. Documentation and paper

- `notes/decision_log.md`: every choice, the alternatives, and why.
- `notes/lab_notebook.md`: dated entries of what was run and what was learned.
- Paper sections: abstract, introduction, related work, methods, results, analysis, limitations.
- Isaias plans a personal write-up for his website. Get advisor approval first, and credit Ryan's contributions clearly.

## 19. References (verify before citing)

- O'Neil et al. 2016, Merck combination screen (Molecular Cancer Therapeutics)
- DrugComb (Zagidullin 2019; Zheng 2021)
- NCI-ALMANAC (Holbeck et al. 2017)
- Therapeutics Data Commons (Huang et al. 2021)
- RECOVER (Bertin et al.): sequential optimization for drug combinations
- BATCHIE (Tosh et al.): Bayesian active learning for combination screens
- CancerGPT (Li et al.): LLM synergy prediction
- BioDiscoveryAgent (Roohani et al.): LLM agent for experiment design, closest analog
- SHELDON (Joshi, Shethia, Lam, submitted); DataSTORM (Liu et al., COLM 2026)
