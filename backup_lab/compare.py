"""Discovery curves and summary table (backup copy of Ryan's experiments/compare.py, plan Section 9).

For each method: cumulative number of strong combinations found vs experiments run, mean ± std over seeds.
Strong flags are recomputed here from the lab's full non-held-out results (top 5%, or --quantile 0.99).
Outputs results/<source>/figures/discovery_<outcome>_top<pct>.png and summary_<outcome>_top<pct>.csv.
  strong_at_250  strong combinations found with the full budget
  auc            mean of the cumulative curve divided by its maximum possible value (1 = found one every pick)

Usage: python -m backup_lab.compare --outcome synergy"""
import argparse
import re

import matplotlib
import numpy as np
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from agent.lab_source import SOURCES, get_source, make_lab, results_dir, truth_for  # noqa: E402
from backup_lab.thresholds import strong_thresholds  # noqa: E402

PATTERN = re.compile(r"run_log_(?P<method>.+)_(?P<outcome>synergy|inhibition)_seed(?P<seed>\d+)\.csv")


def curves(out_dir, outcome, cutoff):
    found = {}
    for path in sorted(out_dir.glob("run_log_*.csv")):
        m = PATTERN.fullmatch(path.name)
        if not m or m["outcome"] != outcome:
            continue
        log = pd.read_csv(path)
        found.setdefault(m["method"], []).append(np.cumsum(log[outcome].to_numpy() >= cutoff))
    return found


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--outcome", choices=["synergy", "inhibition"], default="synergy")
    p.add_argument("--quantile", type=float, default=0.95)
    p.add_argument("--lab", choices=SOURCES, default=None)
    args = p.parse_args()

    source = get_source(args.lab)
    out_dir = results_dir(source)
    cutoff = strong_thresholds(truth_for(make_lab(source)), (args.quantile,))[(args.outcome, args.quantile)]
    found = curves(out_dir, args.outcome, cutoff)
    if not found:
        raise SystemExit(f"no run logs for {args.outcome} in {out_dir}")

    tag = f"{args.outcome}_top{round((1 - args.quantile) * 100)}"
    rows = []
    fig, ax = plt.subplots(figsize=(7, 4.5))
    for method, runs in sorted(found.items()):
        n = min(len(r) for r in runs)
        arr = np.stack([r[:n] for r in runs])
        mean, std, x = arr.mean(0), arr.std(0), np.arange(1, n + 1)
        ax.plot(x, mean, label=f"{method} (n={len(runs)})")
        ax.fill_between(x, mean - std, mean + std, alpha=0.2)
        auc = arr.mean(1) / x[-1]
        rows.append({"method": method, "seeds": len(runs), "strong_at_end_mean": arr[:, -1].mean(),
                     "strong_at_end_std": arr[:, -1].std(), "auc_mean": auc.mean(), "auc_std": auc.std(),
                     "experiments": n})
    ax.plot(x, x * (1 - args.quantile), "k:", label="expected by chance")
    ax.set_xlabel("experiments run")
    ax.set_ylabel(f"strong {args.outcome} combinations found")
    ax.set_title(f"Discovery curve, {args.outcome}, top {round((1 - args.quantile) * 100)}% "
                 f"(cutoff {cutoff:.2f}), lab={source}")
    ax.legend()
    fig.tight_layout()
    (out_dir / "figures").mkdir(exist_ok=True)
    fig.savefig(out_dir / "figures" / f"discovery_{tag}.png", dpi=150)
    summary = pd.DataFrame(rows).round(3)
    summary.to_csv(out_dir / f"summary_{tag}.csv", index=False)
    print(f"cutoff {cutoff:.2f}\n{summary.to_string(index=False)}")


if __name__ == "__main__":
    main()
