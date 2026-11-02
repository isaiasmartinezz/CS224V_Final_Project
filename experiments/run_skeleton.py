"""Run the skeleton agent against the stand-in lab and save results/run_log_<method>_seed<N>.csv.
Strong-combination flags are added here, after the run, so the agent never sees thresholds.

Usage: python experiments/run_skeleton.py --seeds 0 1 2 3 4"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent.agent import run_agent  # noqa: E402
from agent.stand_in_lab import StandInLab  # noqa: E402

RESULTS = Path("results")
STRONG_QUANTILE = 0.95  # top 5% (plan Section 6)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--seeds", type=int, nargs="+", default=[0])
    parser.add_argument("--method", default="agent_random")
    args = parser.parse_args()

    for seed in args.seeds:
        lab = StandInLab(seed=0)  # same fake world every seed; only the agent's choices vary
        log = run_agent(lab, seed=seed)

        truth = lab._all_results()
        for outcome in ["synergy", "inhibition"]:
            cutoff = truth[outcome].quantile(STRONG_QUANTILE)
            log[f"is_strong_{outcome}"] = log[outcome] >= cutoff

        out = RESULTS / f"run_log_{args.method}_seed{seed}.csv"
        log.to_csv(out, index=False)
        print(f"seed {seed}: {len(log)} experiments, {log['round'].nunique()} rounds, "
              f"strong synergy {log['is_strong_synergy'].sum()}, "
              f"strong inhibition {log['is_strong_inhibition'].sum()} -> {out}")


if __name__ == "__main__":
    main()
