# Cancer-Combo-Agent (CS 224V, Fall 2026)

Read `notes/project_plan.md` first. It has the full plan, timeline, definitions, and open questions.
Read `notes/interface.md` for the contract between the simulated lab and the agent.
Read `notes/milestones.md` for milestones and the week-by-week task checklist. Work through Isaias's tasks in order and check them off when done.

## Quick context
- Question: can an LLM agent using literature evidence find strong cancer drug combinations in fewer experiments than random, uncertainty sampling, and Bayesian optimization? Do its mechanistic explanations predict which held-out cell lines respond?
- Data: O'Neil 2016 screen (via DrugComb or TDC) used as a simulated lab. 250 experiments per method, batches of 10, at least 5 seeds.
- Isaias owns `agent/`, literature retrieval, and `data/drug_annotations.csv`. Ryan owns `lab/` (data pipeline, simulated lab, response model, baselines).

## Working rules
- Python 3.11 in `.venv`. Activate with `source .venv/bin/activate`.
- Explain each step simply before doing it. Isaias wants plain-language explanations.
- Commit after each finished task with a clear message.
- Don't edit Ryan's folders without saying so first.
- Never put API keys in code; read them from `.env`.
- Never guess biomedical facts. Mark unknowns as "unknown" and note sources.
- The agent must never see hidden results (see Leakage controls in the plan).
- Record design decisions in `notes/decision_log.md` and progress in `notes/lab_notebook.md`.

## Current status (Nov 2)
- Track tasks in `notes/milestones.md` (check boxes as done).
- Done: environment, repo structure, interface doc, agent skeleton (`python -m agent.agent`, runs against `agent/stub_lab.py`), drug annotations (`data/drug_annotations.csv`), Week 1 Monday update.
- Waiting: Isaias's hand sign-off on annotation rows; drug spellings vs Ryan's cleaned data; Ryan's `SimLab`.
- Done (Nov 9): PubMed retrieval (`agent/retrieval.py`) with cache and exclusion list.
- Done (Nov 9): LLM prompts (`agent/prompts.py`), model = claude-opus-5-5; live check waits on a real API key in `.env`.
- Done (Nov 9): hypothesis tracking, explanations, full LLM loop (`python -m agent.agent --chooser llm`), tested offline with a fake Claude.
- Done (Nov 9): backup copy of Ryan's tasks in `backup_lab/` (real O'Neil data from DrugComb/Zenodo, SimLab, response model, baselines, curves). Switch with `LAB_SOURCE=backup|ryan|stub` in `.env` or `--lab`; results in `results/<source>/`.
- Next: first real run once the API key is set; swap in SimLab when Ryan pushes it; Sat/Sun checks in milestones.
