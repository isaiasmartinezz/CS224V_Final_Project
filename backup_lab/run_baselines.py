"""Run baselines against the lab chosen by LAB_SOURCE (backup copy of Ryan's runner).

Every method goes through agent.agent.run_agent, so all share the same first batch per seed.
Writes results/<source>/run_log_<method>_<outcome>_seed<N>.csv (same columns as the agent's log).

Usage: python -m backup_lab.run_baselines --methods random uncertainty bo --seeds 0 1 2 3 4 --outcome synergy"""
import argparse
import time

from agent.agent import add_strong_flags, run_agent
from agent.lab_source import SOURCES, cell_line_tissue, get_source, make_lab, results_dir, truth_for
from backup_lab.baselines import make_baseline

METHODS = ("random", "uncertainty", "bo")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--methods", nargs="+", choices=METHODS, default=list(METHODS))
    p.add_argument("--seeds", type=int, nargs="+", default=[0])
    p.add_argument("--outcome", choices=["synergy", "inhibition"], default="synergy")
    p.add_argument("--lab", choices=SOURCES, default=None)
    args = p.parse_args()

    source = get_source(args.lab)
    out_dir, tissue = results_dir(source), cell_line_tissue(source)
    print(f"lab source: {source}")
    for method in args.methods:
        for seed in args.seeds:
            t0 = time.time()
            lab = make_lab(source)
            chooser = make_baseline(method, outcome=args.outcome, tissue=tissue, seed=seed)
            log = add_strong_flags(run_agent(lab, seed=seed, chooser=chooser), truth_for(lab))
            out = out_dir / f"run_log_{method}_{args.outcome}_seed{seed}.csv"
            log.to_csv(out, index=False)
            print(f"{method:12} seed {seed}: strong {args.outcome} found "
                  f"{int(log[f'is_strong_{args.outcome}'].sum())}/250 ({time.time() - t0:.0f}s) -> {out}")


if __name__ == "__main__":
    main()
