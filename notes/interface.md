# Interface: Fake Lab <-> Agent

Draft for Ryan and Isaias to agree on before building.

## 1. The fake lab (Ryan) — `lab/sim_lab.py`

A class called `SimLab` with three things:

### `lab.candidates()`
Returns every experiment the agent is allowed to pick, as a table:

| column     | meaning                                  |
|------------|------------------------------------------|
| exp_id     | unique ID for this experiment            |
| drug_a     | first drug name                          |
| drug_b     | second drug name                         |
| cell_line  | cancer cell line name                    |

Held-out cell lines are NOT included here.

### `lab.run(exp_ids)`
Takes a list of exp_ids. Returns their hidden results:

| column      | meaning                                   |
|-------------|-------------------------------------------|
| exp_id      | same ID                                   |
| synergy     | synergy score (metric TBD: ZIP/Loewe/Bliss) |
| inhibition  | growth inhibition score (CSS)             |

Rules:
- Each exp_id counts once against the budget.
- Running the same exp_id twice is an error.
- Running past the budget is an error.

### `lab.budget_remaining()`
Returns how many experiments are left (starts at 250).

## 2. The agent (Isaias) — `agent/agent.py`

A function `run_agent(lab, batch_size=10)` that:
1. Gets candidates from the lab
2. Picks a batch of exp_ids
3. Calls `lab.run(...)`
4. Logs what it picked, what came back, and why
5. Repeats until the budget is 0

## 3. Shared files

| file                              | owner  | contents                          |
|-----------------------------------|--------|-----------------------------------|
| data/processed/oneil_clean.csv    | Ryan   | one row per drug pair + cell line |
| data/processed/heldout_lines.txt  | Ryan   | ~10 held-out cell line names      |
| data/drug_annotations.csv         | Isaias | drug, target, class, mechanism, SMILES |
| results/run_log_<method>.csv      | both   | one row per experiment run        |

## 4. Definitions

- "Strong" combination = top 5% of all experiments, for each outcome separately
  (top 1% as a backup check)
- Budget = 250 experiments per method
- Batch size = 10 per round (25 rounds)

## Open questions
- Which synergy score? (ask research team)
- Batch size 10 OK?
