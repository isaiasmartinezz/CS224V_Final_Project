"""How good is the response model, and does its uncertainty mean anything? (plan 8.1; Week 3 task)

For several training sizes, train on a random sample of non-held-out experiments and predict
2,000 other ones. Reports, for synergy and inhibition, with and without cell-line genetics:
  spearman        rank correlation of prediction vs truth (1 = perfect order)
  within_1sd      share of true values within mean ± 1 std (about 0.68 if uncertainty is calibrated)
  within_2sd      same for ± 2 std (about 0.95 if calibrated)
  err_vs_std      rank correlation of |error| with std (> 0 = the model knows when it is unsure)
Uses tuning seeds 100-104, separate from the reporting seeds 0-4.
Evaluation tool: reads all results directly, never used inside a run.

Usage: python -m backup_lab.model_check"""
import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from agent.lab_source import cell_line_tissue, line_features_for, make_lab, results_dir
from backup_lab.response_model import ResponseModel

SIZES, SEEDS, N_TEST = (50, 100, 250), (100, 101, 102, 103, 104), 2000


def check(truth, outcome, n_train, seed, genetics, tissue):
    rng = np.random.default_rng(seed)
    idx = rng.permutation(len(truth))
    train, test = truth.iloc[idx[:n_train]], truth.iloc[idx[n_train:n_train + N_TEST]]
    model = ResponseModel(truth["cell_line"].unique(), tissue=tissue, seed=seed, line_features=genetics)
    mean, std = model.fit(train, outcome).predict(test)
    y = test[outcome].to_numpy()
    z = np.abs(y - mean) / np.maximum(std, 1e-9)
    return {"spearman": spearmanr(mean, y)[0], "within_1sd": (z <= 1).mean(), "within_2sd": (z <= 2).mean(),
            "err_vs_std": spearmanr(np.abs(y - mean), std)[0]}


def main():
    truth = make_lab("backup")._all_results().reset_index()
    tissue, gen = cell_line_tissue("backup"), line_features_for("backup")
    rows = []
    for outcome in ("synergy", "inhibition"):
        for label, g in (("no genetics", None), ("with genetics", gen)):
            for n in SIZES:
                res = pd.DataFrame([check(truth, outcome, n, s, g, tissue) for s in SEEDS]).mean()
                rows.append({"outcome": outcome, "features": label, "n_train": n, **res.round(3).to_dict()})
                print(rows[-1], flush=True)
    out = results_dir("backup") / "model_check.csv"
    pd.DataFrame(rows).to_csv(out, index=False)
    print(f"-> {out}")


if __name__ == "__main__":
    main()
