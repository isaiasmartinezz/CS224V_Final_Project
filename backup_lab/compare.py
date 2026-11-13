"""Discovery curves and summary table (plan Section 9).

For each run log: cumulative number of strong combinations found vs experiments run, mean ± std over seeds.
"Strong" comes from backup_lab/thresholds.py and is looked up by exp_id from the lab's full
non-held-out results (never from the log), so any definition can be applied to any run afterwards.
  --definition joint_within_line (default, primary) | joint (secondary) | synergy | inhibition [--quantile 0.95]
For the joint definitions every run is shown, labeled by what it optimized ("bo:synergy").
Outputs results/<dir>/figures/discovery_<tag>.png, summary_<tag>.csv, strong_by_line.csv.
  strong_at_end      strong combinations found with the full budget
  auc                mean of the cumulative curve divided by its maximum (1 = a strong one every pick)
  top5_line_share    share of picks in the 5 lines with the highest mean inhibition (sensitive-line bias)

Usage: python -m backup_lab.compare   (primary definition; add --definition joint for the secondary one)"""
import argparse
import re

import matplotlib
import numpy as np
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from agent.lab_source import SOURCES, get_source, make_lab, results_dir, truth_for  # noqa: E402
from backup_lab.thresholds import DEFINITIONS, OUTCOMES, PRIMARY, strong_by_line, strong_labels  # noqa: E402

PATTERN = re.compile(r"run_log_(?P<method>.+)_(?P<target>synergy|inhibition|joint)_seed(?P<seed>\d+)\.csv")


def load_runs(out_dir, definition, include=None):
    """{label: [log, ...]}; single-score definitions only use runs that optimized that score."""
    runs = {}
    for path in sorted(out_dir.glob("run_log_*.csv")):
        m = PATTERN.fullmatch(path.name)
        if not m or (definition in OUTCOMES and m["target"] != definition):
            continue
        if include and not re.fullmatch(include, f"{m['method']}:{m['target']}"):
            continue
        label = m["method"] if definition in OUTCOMES else f"{m['method']}:{m['target']}"
        runs.setdefault(label, []).append(pd.read_csv(path))
    return runs


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--definition", choices=DEFINITIONS, default=PRIMARY)
    p.add_argument("--quantile", type=float, default=0.95, help="single-score definitions only")
    p.add_argument("--lab", choices=SOURCES, default=None)
    p.add_argument("--subdir", default="", help="e.g. tuning: keeps tuning runs apart from reported runs")
    p.add_argument("--include", default=None, help="regex on 'method:target', e.g. '(random|bo):joint'")
    p.add_argument("--name", default="", help="suffix for the output files")
    args = p.parse_args()

    source = get_source(args.lab)
    out_dir = results_dir(source)
    out_dir = out_dir / args.subdir if args.subdir else out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    truth = truth_for(make_lab(source))
    labels, info = strong_labels(truth, args.definition, args.quantile)
    sensitive = set(truth.groupby("cell_line")["inhibition"].mean().nlargest(5).index)
    runs = load_runs(out_dir, args.definition, args.include)
    if not runs:
        raise SystemExit(f"no run logs for {args.definition} in {out_dir}")

    tag = args.definition + (f"_top{round((1 - args.quantile) * 100)}" if args.definition in OUTCOMES else "") + args.name
    rate = float(labels.mean())
    rows = []
    fig, ax = plt.subplots(figsize=(7.5, 4.8))
    for label, logs in sorted(runs.items()):
        n = min(len(l) for l in logs)
        arr = np.stack([np.cumsum(l["exp_id"].map(labels).fillna(False).to_numpy(bool)[:n]) for l in logs])
        mean, std, x = arr.mean(0), arr.std(0), np.arange(1, n + 1)
        ax.plot(x, mean, label=f"{label} (n={len(logs)})")
        ax.fill_between(x, mean - std, mean + std, alpha=0.15)
        auc = arr.mean(1) / x[-1]
        line_share = [l["cell_line"][:n].isin(sensitive).mean() for l in logs]
        rows.append({"method": label, "seeds": len(logs), "strong_at_end_mean": arr[:, -1].mean(),
                     "strong_at_end_std": arr[:, -1].std(), "auc_mean": auc.mean(), "auc_std": auc.std(),
                     "top5_line_share": np.mean(line_share), "experiments": n})
    ax.plot(x, x * rate, "k:", label="expected by chance")
    ax.set_xlabel("experiments run")
    ax.set_ylabel("strong combinations found")
    ax.set_title(f"Discovery curve: {tag} ({rate:.0%} strong), lab={out_dir.name}")
    ax.legend(fontsize=8)
    fig.tight_layout()
    (out_dir / "figures").mkdir(exist_ok=True)
    fig.savefig(out_dir / "figures" / f"discovery_{tag}.png", dpi=150)
    summary = pd.DataFrame(rows).sort_values("strong_at_end_mean", ascending=False).round(3)
    summary.to_csv(out_dir / f"summary_{tag}.csv", index=False)
    strong_by_line(truth).to_csv(out_dir / "strong_by_line.csv")
    print(f"{tag}: {info}\nchance at {n}: {n * rate:.1f}; 5 most sensitive lines = "
          f"{len(sensitive) / truth['cell_line'].nunique():.0%} of lines\n{summary.to_string(index=False)}\n")


if __name__ == "__main__":
    main()
