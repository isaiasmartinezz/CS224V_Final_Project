# Milestones and Weekly Tasks

Companion to `notes/project_plan.md`. Check off tasks as they're done (`- [x]`).
Owner tags: **[I]** Isaias, **[R]** Ryan, **[Both]**.

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
- [ ] Get the exact drug spellings from Ryan's cleaned data; fix `data/drug_names.txt` if any differ; rerun _(blocked: no cleaned data yet)_
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
- [ ] `data/processed/oneil_clean.csv` and `heldout_lines.txt`
- [ ] `lab/sim_lab.py` matching the interface
- [ ] Random baseline run + first discovery curve in `results/`

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
- [ ] `agent/retrieval.py` with `search(query, max_results=10)` using PubMed E-utilities (esearch for IDs, efetch for title + abstract + year + DOI)
- [ ] Cache every query and result to `data/cache/pubmed/` (JSON) so repeat runs don't re-download
- [ ] `agent/excluded_sources.txt` listing O'Neil et al. 2016 (and any paper reporting its screen); filter these out of every result
- [ ] Helper `evidence_for_pair(drug_a, drug_b)`: searches each drug's mechanism plus the pair together; returns a short list of sources with IDs
- [ ] Quick test: run it on 3 well-known pairs and 2 Merck compounds; note what comes back in the lab notebook
- **Done when:** retrieval returns sources for known drugs, uses the cache on repeat calls, and never returns excluded papers

**Wed Nov 4: Prompts and structured outputs**
- [ ] `agent/prompts.py` with three prompts:
  - **Hypothesize:** given drug annotations, cell line info, evidence, and results so far, propose hypotheses as JSON
  - **Critique:** challenge each hypothesis against evidence and observed results; keep, revise, or drop
  - **Select:** choose 10 exp_ids from the shortlist, each with a reason and the hypothesis it tests
- [ ] Every LLM response is JSON validated in code; on bad output, retry once, then fall back to the model's top picks
- [ ] Pick one LLM model for all runs; record the choice in `notes/decision_log.md`
- **Done when:** each prompt returns valid JSON on a hand-made example

**Thu Nov 5: Hypothesis tracking and explanations**
- [ ] `agent/hypotheses.py`: store hypotheses with id, text, drugs, predicted responder cell lines, status (open / supported / refuted), and evidence IDs
- [ ] After each batch, update statuses from the new results
- [ ] `agent/explanations.py`: every flagged combination gets an explanation labeled mechanistic / cross-cancer / statistical; mechanistic ones must include predicted responder cell lines
- [ ] Log every LLM call (prompt, response, model, tokens, cost) to `results/llm_logs/`
- **Done when:** a test run produces hypotheses, status updates, and labeled explanations in the log

**Fri Nov 6: Connect everything**
- [ ] Swap `stub_lab` for Ryan's `SimLab`
- [ ] Shortlist step: use Ryan's response model to keep the top ~50 candidates; if the model isn't ready, shortlist randomly and note it
- [ ] Full agent loop: shortlist → retrieve → hypothesize → critique → select → run → update
- [ ] TA meeting: show the agent running; ask for feedback on prompts and evaluation
- **Done when:** one seed runs all 250 experiments with real retrieval and explanations

**Sat Nov 7 to Sun Nov 8: Check and document**
- [ ] Sanity checks: no exp_id run twice; no held-out cell lines in candidates; no excluded papers in any retrieved evidence
- [ ] Read 10 explanations by hand: are they grounded in the retrieved sources? Note problems
- [ ] Estimate cost per full run (from LLM logs); record it
- [ ] Lab notebook entry for the week; decision log updated
- [ ] Draft Monday update (`notes/weekly_updates/2026-11-09.md`)
- [ ] Commit everything; tell Ryan what changed

**Isaias Week 2 deliverables**
- `agent/retrieval.py`, `agent/prompts.py`, `agent/hypotheses.py`, `agent/explanations.py`, working `agent/agent.py`
- `agent/excluded_sources.txt`, retrieval cache
- One full agent run with real retrieval, its log, and a cost estimate

### Ryan: Week 2
- [ ] Match cell lines to DepMap; save cell line features to `data/processed/`
- [ ] Drug fingerprints from SMILES (RDKit) using `data/drug_annotations.csv`
- [ ] `lab/response_model.py`: predicts both outcomes with uncertainty; retrains after each batch
- [ ] `lab/baselines.py`: uncertainty sampling and Bayesian optimization
- [ ] Discovery curves for all three baselines, 1 seed
- [ ] Function to compute strong-combination thresholds (top 5% and top 1%)

---

## Week 3: Nov 9 to Nov 15 → M3

**[I]**
- [ ] Switch to SHELDON if access is ready (keep PubMed as fallback); confirm exclusion works
- [ ] Tune prompts using Week 2 failures; record changes in the decision log
- [ ] Run agent: 5 seeds × both outcomes
- [ ] Classify explanations by level; count mechanistic ones with valid predictions

**[R]**
- [ ] Run all three baselines: 5 seeds × both outcomes
- [ ] `experiments/compare.py`: discovery curves (mean ± spread), strong combinations at 250, area under curve

**[Both]**
- [ ] Prepare Nov 16 review: results, what's working, what to cut or change
- [ ] Monday update

---

## Week 4: Nov 16 to Nov 22 → M4 (code freeze Nov 22)

**[I]**
- [ ] Ablations: no literature; masked drug names; no critique step
- [ ] Famous vs obscure split: define the groups, rerun analysis by group
- [ ] Held-out mechanism test: score each mechanistic prediction against the held-out lines vs a random-guess baseline

**[R]**
- [ ] Model-only shortlist ablation
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
