"""Temporary stand-in for Ryan's lab/sim_lab.py, so the agent loop can run end to end.
Same methods and rules as notes/interface.md. Scores are RANDOM, not real data.
Delete once SimLab and data/processed/oneil_clean.csv exist."""
from itertools import combinations
from pathlib import Path

import numpy as np
import pandas as pd

DRUG_NAMES = Path("data/drug_names.txt")


class StandInLab:
    def __init__(self, budget=250, n_lines=39, heldout_frac=0.25, seed=0):
        rng = np.random.default_rng(seed)
        drugs = [d.strip() for d in DRUG_NAMES.read_text().splitlines() if d.strip()]
        lines = [f"FAKE_LINE_{i:02d}" for i in range(n_lines)]
        heldout = set(rng.choice(lines, size=round(n_lines * heldout_frac), replace=False))

        rows = [(a, b, c) for a, b in combinations(sorted(drugs), 2) for c in lines]
        table = pd.DataFrame(rows, columns=["drug_a", "drug_b", "cell_line"])
        table.insert(0, "exp_id", [f"E{i:06d}" for i in range(len(table))])

        # Pair effect + cell line effect + noise, so a smarter method has something to find
        pair_effect = table.groupby(["drug_a", "drug_b"]).ngroup().map(
            dict(enumerate(rng.normal(0, 5, len(drugs) ** 2))))
        line_effect = table["cell_line"].map(dict(zip(lines, rng.normal(0, 3, n_lines))))
        table["synergy"] = pair_effect + line_effect + rng.normal(0, 5, len(table))
        table["inhibition"] = 0.5 * pair_effect + line_effect + rng.normal(0, 5, len(table))

        self._hidden = table[~table["cell_line"].isin(heldout)].set_index("exp_id")
        self._heldout = sorted(heldout)
        self._budget = budget
        self._done = set()
        self.calls = []  # every run() call, for replay

    def candidates(self):
        todo = self._hidden.index.difference(sorted(self._done))
        return self._hidden.loc[todo, ["drug_a", "drug_b", "cell_line"]].reset_index()

    def run(self, exp_ids):
        exp_ids = list(exp_ids)
        if len(set(exp_ids)) != len(exp_ids):
            raise ValueError("duplicate exp_id in batch")
        unknown = set(exp_ids) - set(self._hidden.index)
        if unknown:
            raise ValueError(f"unknown or held-out exp_ids: {sorted(unknown)[:5]}")
        repeats = set(exp_ids) & self._done
        if repeats:
            raise ValueError(f"already run: {sorted(repeats)[:5]}")
        if len(exp_ids) > self.budget_remaining():
            raise ValueError(f"over budget: asked {len(exp_ids)}, {self.budget_remaining()} left")
        self._done.update(exp_ids)
        self.calls.append(exp_ids)
        return self._hidden.loc[exp_ids, ["synergy", "inhibition"]].reset_index()

    def budget_remaining(self):
        return self._budget - len(self._done)

    # Evaluation only: the runner uses this after the agent finishes. Never pass it to the agent.
    def _all_results(self):
        return self._hidden[["synergy", "inhibition"]]
