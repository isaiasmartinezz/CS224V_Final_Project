"""Agent loop: pick a batch, run it, log it, repeat until the budget is spent.
Week 1 skeleton: the chooser is random. The LLM chooser will plug into the same slot.

Usage: python -m agent.agent --seeds 0 1 2 3 4"""
import argparse
from pathlib import Path

import anthropic
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


class LLMChooser:
    """Each round: update hypothesis statuses, shortlist, retrieve evidence,
    hypothesize -> critique -> select, and attach a labeled explanation to every pick."""

    def __init__(self, run_id, outcome="synergy", shortlist_size=50, evidence_pairs=6,
                 llm=None, retrieve=None, model=None, tissue=None, explore_frac=0.1, kappa=1.0):
        from agent.hypotheses import HypothesisBook
        from agent.prompts import LLM
        from agent.retrieval import evidence_for_pair

        self.llm = llm or LLM(run_id)
        self.retrieve = retrieve or (lambda a, b: evidence_for_pair(a, b, per_query=3))
        self.book = HypothesisBook()
        self.outcome, self.shortlist_size, self.evidence_pairs = outcome, shortlist_size, evidence_pairs
        self.model, self.tissue, self.explore_frac, self.kappa = model, tissue or {}, explore_frac, kappa
        ann = pd.read_csv("data/drug_annotations.csv", dtype=str).set_index("drug")
        self.annotations = ann.to_dict("index")
        self.round = 0

    def shortlist(self, candidates, history, rng):
        """With a response model (plan 8.3 step 1): top ~90% by mean + kappa*std (the BO score),
        plus the most uncertain ~10%, ordered by BO score. Without one: a random sample."""
        n = min(self.shortlist_size, len(candidates))
        if self.model is None:
            short = candidates.iloc[rng.choice(len(candidates), size=n, replace=False)].reset_index(drop=True)
        else:
            mean, std = self.model.fit(history, self.outcome).predict(candidates)
            order = np.argsort(-(mean + self.kappa * std), kind="stable")
            n_explore = max(1, round(n * self.explore_frac))
            top = order[:n - n_explore]
            rest = np.setdiff1d(np.arange(len(candidates)), top)
            unsure = rest[np.argsort(-std[rest], kind="stable")[:n_explore]]
            keep = np.concatenate([top, unsure])
            short = candidates.iloc[keep].reset_index(drop=True)
            short["pred_mean"], short["pred_std"] = mean[keep].round(2), std[keep].round(2)
        if self.tissue:
            short.insert(4, "tissue", short["cell_line"].map(self.tissue).fillna("unknown"))
        return short

    def __call__(self, candidates, history, k, rng):
        from agent.explanations import explain
        from agent.prompts import critique, hypothesize, select

        self.round += 1
        self.book.update(history, self.outcome, self.round)
        short = self.shortlist(candidates, history, rng)
        pairs = list(dict.fromkeys(zip(short["drug_a"], short["drug_b"])))[:self.evidence_pairs]
        evidence = {f"{a} + {b}": self.retrieve(a, b) for a, b in pairs}

        new = hypothesize(self.llm, short, self.annotations, evidence, history,
                          list(self.book.items.values()), outcome=self.outcome)
        self.book.add(new, self.round)
        if self.book.active():
            self.book.apply_critique(critique(self.llm, self.book.active(), evidence, history, self.outcome),
                                     self.round)
        picks = select(self.llm, short, self.book.active(), history, k=k, outcome=self.outcome)
        return [p.exp_id for p in picks], [explain(p, self.book) for p in picks]


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
    from agent.lab_source import (SOURCES, cell_line_tissue, get_source, make_lab,
                                  make_response_model, results_dir, truth_for)

    parser = argparse.ArgumentParser()
    parser.add_argument("--seeds", type=int, nargs="+", default=[0])
    parser.add_argument("--chooser", choices=["random", "llm"], default="random",
                        help="llm = full agent (needs ANTHROPIC_API_KEY); random = skeleton check")
    parser.add_argument("--outcome", choices=["synergy", "inhibition"], default="synergy")
    parser.add_argument("--lab", choices=SOURCES, default=None,
                        help="whose lab to use; default from LAB_SOURCE in .env, else backup")
    args = parser.parse_args()

    source = get_source(args.lab)
    out_dir = results_dir(source)
    print(f"lab source: {source}")
    method = "agent" if args.chooser == "llm" else "agent_random"
    for seed in args.seeds:
        lab = make_lab(source)
        run_id = f"{source}_{method}_{args.outcome}_seed{seed}"
        if args.chooser == "llm":
            lines = lab.candidates()["cell_line"].unique()
            chooser = LLMChooser(run_id, outcome=args.outcome, tissue=cell_line_tissue(source),
                                 model=make_response_model(source, lines, seed=seed))
        else:
            chooser = random_chooser
        try:
            log = run_agent(lab, seed=seed, chooser=chooser)
        except anthropic.AuthenticationError:
            raise SystemExit("ANTHROPIC_API_KEY in .env is not a valid key. Add a real key and rerun.")
        log = add_strong_flags(log, truth_for(lab))  # after the run, so the agent never sees it
        if args.chooser == "llm":
            chooser.book.save(out_dir / f"hypotheses_{run_id}.json")
            print(f"LLM cost: ${chooser.llm.total_cost:.2f}")
        out = out_dir / f"run_log_{method}_{args.outcome}_seed{seed}.csv"
        log.to_csv(out, index=False)
        print(f"seed {seed}: {len(log)} experiments, {log['round'].nunique()} rounds, "
              f"strong synergy {log['is_strong_synergy'].sum()}, "
              f"strong inhibition {log['is_strong_inhibition'].sum()} -> {out}")


if __name__ == "__main__":
    main()
