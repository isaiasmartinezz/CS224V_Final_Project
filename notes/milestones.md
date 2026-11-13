# Milestones and Weekly Tasks

Companion to `notes/project_plan.md`. Check off tasks as they're done (`- [x]`).
Owner tags: **[I]** Isaias, **[R]** Ryan, **[Both]**.

**Nov 13: Isaias now owns all tasks, including every [R] and [Both] item.** The lab in `backup_lab/` is the official lab.

---

## Milestones at a glance

| # | Milestone | Due | Done when |
|---|---|---|---|
| M1 | End-to-end pipeline | Mon Nov 2 | Random-baseline curve exists; agent completes a 250-experiment run against the lab (or a stand-in) |
| M2 | Real components | Sun Nov 8 | Response model with uncertainty; uncertainty sampling and BO baselines; agent uses real literature retrieval and writes explanations |
| M3 | First comparison | Sun Nov 15 | Agent vs 3 baselines, both outcomes, 5 seeds. Reviewed with team Nov 16 |
| M4 | Stress tests + code freeze | Sun Nov 22 | Ablations, famous vs obscure, held-out mechanism test all run. No new features after this |
| M5 | Final results + paper draft | Sun Nov 29 | Final figures and tables; full paper draft |
| M6 | Presentation | Wed Dec 2 | Dry run Nov 30; present Dec 2 |

---

## Week 1 leftovers (finish Mon Nov 2, before 11:00 sync)

**[I] 1. Drug annotations**
- [x] Run `python data/build_drug_annotations.py` (from your own Terminal or Claude Code)
- [x] Get the exact drug spellings from Ryan's cleaned data; fix `data/drug_names.txt` if any differ; rerun _(blocked: no cleaned data yet)_ _(done Nov 9: DrugComb names mapped to ours by PubChem CID, `backup_lab/clean_oneil.py`)_
- [ ] Review every row: right ChEMBL match, sensible target, fill `drug_class` in plain words _(matches verified, `drug_class` filled with sources; Isaias to read each row and set status to done)_
- [x] Research `NEEDS WORK` rows; cite sources in `notes`; mark unknowns "unknown"
- [x] Save as `data/drug_annotations.csv`; commit
- **Done when:** 38 rows, every row `status = done`, unknowns listed for the team

**[I] 2. Agent skeleton**
- [x] `agent/stub_lab.py`: a stand-in lab matching `notes/interface.md` that returns random scores (delete once Ryan's lab works)
- [x] `agent/agent.py`: `run_agent(lab, batch_size=10, seed=0)` loops until budget is 0, picking randomly for now
- [x] Writes `results/run_log_agent_seed0.csv` in the format from project plan Section 11
- [x] Runs from the command line: `python -m agent.agent`
- [x] Commit
- **Done when:** a full 250-experiment run finishes and the log has 250 rows

**[R] 3. Data, lab, random baseline**
- [x] `data/processed/oneil_clean.csv` and `heldout_lines.txt` _(backup done by Isaias in `backup_lab/`, see LAB_SOURCE)_
- [x] `lab/sim_lab.py` matching the interface _(backup done by Isaias in `backup_lab/`, see LAB_SOURCE)_
- [x] Random baseline run + first discovery curve in `results/` _(backup done by Isaias in `backup_lab/`, see LAB_SOURCE)_

**[I] 4. Monday update (due noon)**
- [x] Write `notes/weekly_updates/2026-11-02.md` using the template in project plan Section 17
- [x] List open questions for the 12:00 team meeting (project plan Section 14)

---

## Week 2: Nov 2 to Nov 8 → M2

### Isaias: everything needed this week

**Mon Nov 2**
- [ ] Finish Week 1 leftovers above
- [ ] 11:00 sync with Ryan: confirm interface, drug spellings, held-out lines, and when `SimLab` is ready
- [ ] 12:00 team meeting: ask open questions; record answers in `notes/decision_log.md` and update project plan Section 14

**Tue Nov 3: Literature retrieval (placeholder until SHELDON)**
- [x] `agent/retrieval.py` with `search(query, max_results=10)` using PubMed E-utilities (esearch for IDs, efetch for title + abstract + year + DOI)
- [x] Cache every query and result to `data/cache/pubmed/` (JSON) so repeat runs don't re-download
- [x] `agent/excluded_sources.txt` listing O'Neil et al. 2016 (and any paper reporting its screen); filter these out of every result
- [x] Helper `evidence_for_pair(drug_a, drug_b)`: searches each drug's mechanism plus the pair together; returns a short list of sources with IDs
- [x] Quick test: run it on 3 well-known pairs and 2 Merck compounds; note what comes back in the lab notebook
- **Done when:** retrieval returns sources for known drugs, uses the cache on repeat calls, and never returns excluded papers

**Wed Nov 4: Prompts and structured outputs**
- [x] `agent/prompts.py` with three prompts:
  - **Hypothesize:** given drug annotations, cell line info, evidence, and results so far, propose hypotheses as JSON
  - **Critique:** challenge each hypothesis against evidence and observed results; keep, revise, or drop
  - **Select:** choose 10 exp_ids from the shortlist, each with a reason and the hypothesis it tests
- [x] Every LLM response is JSON validated in code; on bad output, retry once, then fall back to the model's top picks
- [x] Pick one LLM model for all runs; record the choice in `notes/decision_log.md`
- **Done when:** each prompt returns valid JSON on a hand-made example _(offline tests pass; live run `python experiments/try_prompts.py` waits on a real API key in `.env`)_

**Thu Nov 5: Hypothesis tracking and explanations**
- [x] `agent/hypotheses.py`: store hypotheses with id, text, drugs, predicted responder cell lines, status (open / supported / refuted), and evidence IDs
- [x] After each batch, update statuses from the new results
- [x] `agent/explanations.py`: every flagged combination gets an explanation labeled mechanistic / cross-cancer / statistical; mechanistic ones must include predicted responder cell lines
- [x] Log every LLM call (prompt, response, model, tokens, cost) to `results/llm_logs/`
- **Done when:** a test run produces hypotheses, status updates, and labeled explanations in the log _(done with a fake Claude in `tests/test_agent_llm.py`; real-LLM run waits on API key)_

**Fri Nov 6: Connect everything**
- [x] Swap `stub_lab` for Ryan's `SimLab` _(uses backup SimLab via LAB_SOURCE; `--lab ryan` once his lands)_
- [x] Shortlist step: use Ryan's response model to keep the top ~50 candidates; if the model isn't ready, shortlist randomly and note it _(uses the backup response model; random only with the stub lab)_
- [x] Full agent loop: shortlist → retrieve → hypothesize → critique → select → run → update
- [ ] TA meeting: show the agent running; ask for feedback on prompts and evaluation
- **Done when:** one seed runs all 250 experiments with real retrieval and explanations _(`python -m agent.agent --chooser llm`; waits on API key)_

**Sat Nov 7 to Sun Nov 8: Check and document**
- [x] Sanity checks: no exp_id run twice; no held-out cell lines in candidates; no excluded papers in any retrieved evidence _(done Nov 13: `experiments/sanity_checks.py`, all pass)_
- [ ] Read 10 explanations by hand: are they grounded in the retrieved sources? Note problems
- [x] Estimate cost per full run (from LLM logs); record it _(estimate Nov 13: `experiments/estimate_cost.py`; real number after first run)_
- [ ] Lab notebook entry for the week; decision log updated
- [ ] Draft Monday update (`notes/weekly_updates/2026-11-09.md`)
- [ ] Commit everything; tell Ryan what changed

**Isaias Week 2 deliverables**
- `agent/retrieval.py`, `agent/prompts.py`, `agent/hypotheses.py`, `agent/explanations.py`, working `agent/agent.py`
- `agent/excluded_sources.txt`, retrieval cache
- One full agent run with real retrieval, its log, and a cost estimate

### Ryan: Week 2
- [x] Match cell lines to DepMap; save cell line features to `data/processed/` _(done Nov 13 with Cell Model Passports; DepMap portal blocks downloads)_
- [x] Drug fingerprints from SMILES (RDKit) using `data/drug_annotations.csv` _(backup done by Isaias in `backup_lab/`, see LAB_SOURCE)_
- [x] `lab/response_model.py`: predicts both outcomes with uncertainty; retrains after each batch _(backup done by Isaias in `backup_lab/`, see LAB_SOURCE)_
- [x] `lab/baselines.py`: uncertainty sampling and Bayesian optimization _(backup done by Isaias in `backup_lab/`, see LAB_SOURCE)_
- [x] Discovery curves for all three baselines, 1 seed _(backup done by Isaias in `backup_lab/`, see LAB_SOURCE)_
- [x] Function to compute strong-combination thresholds (top 5% and top 1%) _(backup done by Isaias in `backup_lab/`, see LAB_SOURCE)_

---

## Week 3: Nov 9 to Nov 15 → M3

**[Both] Definitions locked with research team (Nov 13)**
- [x] Loewe synergy (Bliss robustness check), CSS inhibition
- [x] Strong = joint Loewe + CSS cutoff, ranked within each cell line (primary); all-experiments joint (secondary)
- [x] Baselines rerun under the new definitions (5 seeds, Loewe and Bliss)
- [x] No-LLM control (model picks from its own top 50): main control, run with the first real agent runs _(BO = this control, tested; plus new shortlist_random control; both run, 5 seeds)_
- [x] Decide whether baselines should optimize the joint goal directly _(done: baselines and agent default to the joint target)_

**[I]**
- [ ] Switch to SHELDON if access is ready (keep PubMed as fallback); confirm exclusion works
- [ ] Tune prompts using Week 2 failures; record changes in the decision log
- [ ] Run agent: 5 seeds × both outcomes
- [ ] Classify explanations by level; count mechanistic ones with valid predictions

**[R]**
- [x] Run all three baselines: 5 seeds × both outcomes _(done Nov 13 with joint target + genetics)_
- [x] `experiments/compare.py`: discovery curves (mean ± spread), strong combinations at 250, area under curve _(`backup_lab/compare.py`)_

**[Both]**
- [ ] Prepare Nov 16 review: results, what's working, what to cut or change
- [ ] Monday update

---

## Week 4: Nov 16 to Nov 22 → M4 (code freeze Nov 22)

**[I]**
- [ ] Ablations: no literature; masked drug names; no critique step _(built: `--ablation`; tested offline; runs wait on key)_
- [x] Famous vs obscure split: define the groups, rerun analysis by group _(groups by PubMed count, `backup_lab/familiarity.py`; baselines analyzed; agent waits on key)_
- [ ] Held-out mechanism test: score each mechanistic prediction against the held-out lines vs a random-guess baseline _(built: `predict_heldout` + `backup_lab/mechanism_test.py`; runs wait on key)_

**[R]**
- [x] Model-only shortlist ablation _(= BO, tested; shortlist_random added)_
- [ ] Sensitivity check at top 1%
- [ ] Final plotting scripts

**[Both]**
- [ ] Freeze code Nov 22; tag the commit `code-freeze`

---

## Week 5: Nov 23 to Nov 29 → M5

**[I]**
- [ ] Paper: introduction, related work, agent methods, mechanism-test results, limitations
- [ ] Pick 3 example explanations for the paper and slides

**[R]**
- [ ] Paper: data, lab, response model, baselines, main results
- [ ] Final figures and tables

**[Both]**
- [ ] Slides draft
- [ ] Verify every reference and every number in the paper against logs

---

## Week 6: Nov 30 to Dec 2 → M6

- [ ] **[Both]** Dry run with the team Nov 30; fix feedback
- [ ] **[Both]** Present Dec 2
- [ ] **[I]** After presenting: get advisor approval before any website write-up; credit Ryan
