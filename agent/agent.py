"""Agent loop: pick a batch, run it, log it, repeat until the budget is spent.
Week 1 skeleton: the chooser is random. The LLM chooser will plug into the same slot.

Usage: python -m agent.agent --seeds 0 1 2 3 4"""
import argparse
from pathlib import Path

import numpy as np
import pandas as pd

LOG_COLUMNS = [
    "round", "exp_id", "drug_a", "drug_b", "cell_line", "synergy", "inhibition",
    "hypothesis_id", "explanation_level", "explanation_text", "retrieved_source_ids",
]


def initial_batch(candidates, seed, k):
    """Same first batch for every method with the same seed (plan Section 6).
    Ryan's baselines should call this too so comparisons are fair."""
    rng = np.random.default_rng(seed)
    return list(rng.choice(candidates["exp_id"].to_numpy(), size=k, replace=False))


def random_chooser(candidates, history, k, rng):
    """Returns (exp_ids, explanations). One explanation dict per pick."""
    picks = list(rng.choice(candidates["exp_id"].to_numpy(), size=k, replace=False))
    return picks, [{"explanation_level": "none", "explanation_text": "random pick"}] * k


def run_agent(lab, batch_size=10, chooser=random_chooser, seed=0):
    """Runs until the lab's budget is 0. Returns the run log as a DataFrame.
    The agent only ever sees lab.candidates() and what lab.run() returns."""
    rng = np.random.default_rng(seed + 1)  # separate stream from initial_batch
    history = pd.DataFrame(columns=LOG_COLUMNS)
    round_num = 0
    while lab.budget_remaining() > 0:
        cands = lab.candidates()
        k = min(batch_size, lab.budget_remaining(), len(cands))
        if round_num == 0:
            picks = initial_batch(cands, seed, k)
            notes = [{"explanation_level": "none", "explanation_text": "shared initial batch"}] * k
        else:
            picks, notes = chooser(cands, history, k, rng)

        results = lab.run(picks)
        batch = (cands.set_index("exp_id").loc[picks].reset_index()
                 .merge(results, on="exp_id")
                 .join(pd.DataFrame(notes)))
        batch["round"] = round_num
        history = pd.concat([history, batch], ignore_index=True)[LOG_COLUMNS]
        round_num += 1
    return history


def add_strong_flags(log, truth, quantile=0.95):
    """Evaluation only, applied after the run: top 5% of all non-held-out results (plan Section 6)."""
    for outcome in ["synergy", "inhibition"]:
        log[f"is_strong_{outcome}"] = log[outcome] >= truth[outcome].quantile(quantile)
    return log


def main():
    from agent.stub_lab import StubLab  # swap for lab.sim_lab.SimLab once it exists

    parser = argparse.ArgumentParser()
    parser.add_argument("--seeds", type=int, nargs="+", default=[0])
    args = parser.parse_args()

    Path("results").mkdir(exist_ok=True)
    for seed in args.seeds:
        lab = StubLab(seed=0)  # same fake world every seed; only the agent's choices vary
        log = run_agent(lab, seed=seed)
        log = add_strong_flags(log, lab._all_results())  # after the run, so the agent never sees it
        out = Path("results") / f"run_log_agent_seed{seed}.csv"
        log.to_csv(out, index=False)
        print(f"seed {seed}: {len(log)} experiments, {log['round'].nunique()} rounds, "
              f"strong synergy {log['is_strong_synergy'].sum()}, "
              f"strong inhibition {log['is_strong_inhibition'].sum()} -> {out}")


if __name__ == "__main__":
    main()
