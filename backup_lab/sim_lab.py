"""Simulated lab backed by the real O'Neil 2016 results (backup copy of Ryan's lab/sim_lab.py).
Follows notes/interface.md exactly. Turned on/off with LAB_SOURCE (see agent/lab_source.py)."""
from pathlib import Path

import pandas as pd

DATA = Path("data/processed/backup/oneil_clean.csv")
HELDOUT = Path("data/processed/backup/heldout_lines.txt")


class SimLab:
    def __init__(self, data_path=DATA, heldout_path=HELDOUT, budget=250, synergy_metric=None):
        table = pd.read_csv(data_path)
        if synergy_metric:  # e.g. "loewe" -> use synergy_loewe as the synergy column
            table["synergy"] = table[f"synergy_{synergy_metric}"]
        heldout = {l.strip() for l in Path(heldout_path).read_text().splitlines() if l.strip()}
        missing = heldout - set(table["cell_line"])
        if missing:
            raise ValueError(f"held-out lines not in data: {sorted(missing)}")
        table = table.set_index("exp_id")
        self._hidden = table[~table["cell_line"].isin(heldout)]
        self._heldout_table = table[table["cell_line"].isin(heldout)]
        self._heldout = sorted(heldout)
        self._budget = budget
        self._done = set()
        self.calls = []  # every run() call in order, so a run can be replayed

    def candidates(self):
        """Every non-held-out experiment not yet run."""
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

    # ---- Evaluation only: used by runners after a run finishes. Never pass these to a method. ----
    def _all_results(self):
        return self._hidden[["drug_a", "drug_b", "cell_line", "synergy", "inhibition"]]

    def _heldout_results(self):
        return self._heldout_table[["drug_a", "drug_b", "cell_line", "synergy", "inhibition"]]
