"""Run baselines and controls against the lab chosen by LAB_SOURCE.

Every method goes through agent.agent.run_agent, so all share the same first batch per seed.
Writes results/<source>/run_log_<method>_<outcome>_seed<N>.csv (same columns as the agent's log).

Usage: python -m backup_lab.run_baselines --seeds 0 1 2 3 4 --outcome joint"""
import argparse
import time

from agent.agent import add_strong_flags, run_agent
from agent.lab_source import (SOURCES, cell_line_tissue, get_source, line_features_for, make_lab,
                              results_dir, truth_for)
from agent.targets import TARGETS
from backup_lab.baselines import KAPPA, METHODS, make_baseline


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--methods", nargs="+", choices=METHODS, default=list(METHODS))
    p.add_argument("--seeds", type=int, nargs="+", default=[0])
    p.add_argument("--outcome", choices=TARGETS, default="joint", help="what the methods maximize")
    p.add_argument("--kappa", type=float, default=KAPPA)
    p.add_argument("--tag", default="", help="suffix for the method name, e.g. _k2 for a kappa sweep")
    p.add_argument("--no-genetics", action="store_true", help="model without cell-line genetics")
    p.add_argument("--lab", choices=SOURCES, default=None)
    p.add_argument("--subdir", default="", help="e.g. tuning: keeps tuning runs apart from reported runs")
    args = p.parse_args()

    source = get_source(args.lab)
    out_dir, tissue = results_dir(source), cell_line_tissue(source)
    out_dir = out_dir / args.subdir if args.subdir else out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    genetics = None if args.no_genetics else line_features_for(source)
    print(f"lab source: {source}")
    for method in args.methods:
        for seed in args.seeds:
            t0 = time.time()
            lab = make_lab(source)
            chooser = make_baseline(method, outcome=args.outcome, tissue=tissue, seed=seed,
                                    kappa=args.kappa, line_features=genetics)
            log = add_strong_flags(run_agent(lab, seed=seed, chooser=chooser), truth_for(lab))
            out = out_dir / f"run_log_{method}{args.tag}_{args.outcome}_seed{seed}.csv"
            log.to_csv(out, index=False)
            print(f"{method + args.tag:16} seed {seed}: strong (primary) "
                  f"{int(log['is_strong_joint_within_line'].sum())}/250 ({time.time() - t0:.0f}s) -> {out}")


if __name__ == "__main__":
    main()
