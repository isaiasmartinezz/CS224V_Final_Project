"""Agent loop: pick a batch, run it, log it, repeat until the budget is spent.
Week 1 skeleton: the chooser is random. The LLM chooser will plug into the same slot.

Usage: python -m agent.agent --seeds 0 1 2 3 4"""
import argparse
import re
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


ABLATIONS = ("none", "no_literature", "no_critique", "masked_names")


class DrugMask:
    """Masked-names ablation (plan 9.2): every drug name the LLM sees becomes "Drug 01".."Drug 38".
    Annotations keep only class and targets (no names, SMILES, or IDs); names inside retrieved
    titles/abstracts are replaced too. Limitation: brand names or synonyms not in the annotation
    table could still slip through in abstracts."""

    def __init__(self, annotations):
        self.code = {d: f"Drug {i + 1:02d}" for i, d in enumerate(sorted(annotations))}
        self.names = {}
        for d, a in annotations.items():
            for n in {d, a.get("search_name"), a.get("chembl_name")}:
                if isinstance(n, str) and n not in ("unknown", "") and len(n) > 2:
                    self.names[n] = self.code[d]
        self._pattern = re.compile("|".join(re.escape(n) for n in sorted(self.names, key=len, reverse=True)),
                                   re.IGNORECASE)
        self._lower = {n.lower(): c for n, c in self.names.items()}

    def text(self, s):
        return self._pattern.sub(lambda m: self._lower[m.group(0).lower()], s) if isinstance(s, str) else s

    def table(self, df):
        out = df.copy()
        for c in ("drug_a", "drug_b"):
            if c in out:
                out[c] = out[c].map(self.code)
        return out

    def annotations(self, ann):
        return {self.code[d]: {"drug_class": self.text(a.get("drug_class", "unknown")),
                               "targets": a.get("targets", "unknown")} for d, a in ann.items()}

    def evidence(self, ev):
        return {self.text(pair): {part: [{**p, "title": self.text(p["title"]), "abstract": self.text(p["abstract"])}
                                         for p in papers] for part, papers in parts.items()}
                for pair, parts in ev.items()}


class LLMChooser:
    """Each round: update hypothesis statuses, shortlist, retrieve evidence,
    hypothesize -> critique -> select, and attach a labeled explanation to every pick.

    outcome: synergy | inhibition | joint (see agent/targets.py).
    ablation: none | no_literature | no_critique | masked_names (plan 9.2).
    line_info: {cell_line: short genetics summary} shown to the LLM (public metadata, not results)."""

    def __init__(self, run_id, outcome="synergy", shortlist_size=50, evidence_pairs=6,
                 llm=None, retrieve=None, model=None, tissue=None, explore_frac=0.1, kappa=1.0,
                 ablation="none", line_info=None):
        from agent.hypotheses import HypothesisBook
        from agent.prompts import LLM
        from agent.retrieval import evidence_for_pair

        assert ablation in ABLATIONS, ablation
        self.llm = llm or LLM(run_id)
        self.retrieve = retrieve or (lambda a, b: evidence_for_pair(a, b, per_query=3))
        self.book = HypothesisBook()
        self.outcome, self.shortlist_size, self.evidence_pairs = outcome, shortlist_size, evidence_pairs
        self.model, self.tissue, self.explore_frac, self.kappa = model, tissue or {}, explore_frac, kappa
        self.ablation, self.line_info = ablation, line_info or {}
        ann = pd.read_csv("data/drug_annotations.csv", dtype=str).set_index("drug")
        self.annotations = ann.to_dict("index")
        self.mask = DrugMask(self.annotations) if ablation == "masked_names" else None
        self.round = 0

    def shortlist(self, candidates, history, rng):
        from agent.shortlist import make_shortlist
        from agent.targets import with_target
        return make_shortlist(candidates, with_target(history, self.outcome), rng, model=self.model,
                              target=self.outcome, n=self.shortlist_size, explore_frac=self.explore_frac,
                              kappa=self.kappa, tissue=self.tissue)

    def __call__(self, candidates, history, k, rng):
        from agent.explanations import explain
        from agent.prompts import critique, hypothesize, select
        from agent.targets import with_target

        self.round += 1
        short = self.shortlist(candidates, history, rng)
        if self.ablation == "no_literature":
            evidence = {}
        else:
            pairs = list(dict.fromkeys(zip(short["drug_a"], short["drug_b"])))[:self.evidence_pairs]
            evidence = {f"{a} + {b}": self.retrieve(a, b) for a, b in pairs}
        hist, annotations = with_target(history, self.outcome), self.annotations
        if self.mask:  # the LLM and the hypothesis book work entirely in masked names
            short, hist = self.mask.table(short), self.mask.table(hist)
            evidence, annotations = self.mask.evidence(evidence), self.mask.annotations(annotations)
        lines = {l: self.line_info[l] for l in short["cell_line"].unique() if l in self.line_info}

        self.book.update(hist, self.outcome, self.round)
        new = hypothesize(self.llm, short, annotations, evidence, hist, list(self.book.items.values()),
                          outcome=self.outcome, line_info=lines)
        self.book.add(new, self.round)
        if self.book.active() and self.ablation != "no_critique":
            self.book.apply_critique(critique(self.llm, self.book.active(), evidence, hist, self.outcome,
                                              line_info=lines), self.round)
        picks = select(self.llm, short, self.book.active(), hist, k=k, outcome=self.outcome)
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


def add_strong_flags(log, truth):
    """Evaluation only, applied after the run. Adds is_strong_<definition> for the primary definition
    (joint, ranked within cell line), the secondary one (joint), and the single-score top 5%."""
    from backup_lab.thresholds import flag_strong
    for definition in ("joint_within_line", "joint", "synergy", "inhibition"):
        log = flag_strong(log, truth, definition)
    return log


def main():
    import json

    from agent.lab_source import (SOURCES, cell_line_tissue, get_source, line_summaries_for, make_lab,
                                  make_response_model, results_dir, truth_for)
    from agent.prompts import predict_heldout
    from agent.targets import TARGETS

    parser = argparse.ArgumentParser()
    parser.add_argument("--seeds", type=int, nargs="+", default=[0])
    parser.add_argument("--chooser", choices=["random", "llm"], default="random",
                        help="llm = full agent (needs ANTHROPIC_API_KEY); random = skeleton check")
    parser.add_argument("--outcome", choices=TARGETS, default="joint",
                        help="what the agent tries to maximize (joint = both scores, within cell line)")
    parser.add_argument("--ablation", choices=ABLATIONS, default="none")
    parser.add_argument("--lab", choices=SOURCES, default=None,
                        help="which lab to use; default from LAB_SOURCE in .env, else backup")
    args = parser.parse_args()

    source = get_source(args.lab)
    out_dir = results_dir(source)
    print(f"lab source: {source}")
    method = "agent_random" if args.chooser == "random" else (
        "agent" if args.ablation == "none" else f"agent_{args.ablation}")
    summaries = line_summaries_for(source)
    for seed in args.seeds:
        lab = make_lab(source)
        run_id = f"{source}_{method}_{args.outcome}_seed{seed}"
        if args.chooser == "llm":
            lines = lab.candidates()["cell_line"].unique()
            chooser = LLMChooser(run_id, outcome=args.outcome, tissue=cell_line_tissue(source),
                                 model=make_response_model(source, lines, seed=seed),
                                 ablation=args.ablation, line_info=summaries)
        else:
            chooser = random_chooser
        try:
            log = run_agent(lab, seed=seed, chooser=chooser)
            if args.chooser == "llm":
                # Mechanism test (plan 9.3): predict which never-tested lines respond. Names + genetics only.
                heldout_info = {l: summaries.get(l, "genetics unknown") for l in lab._heldout}
                preds = predict_heldout(chooser.llm, list(chooser.book.items.values()), heldout_info, args.outcome)
        except anthropic.AuthenticationError:
            raise SystemExit("ANTHROPIC_API_KEY in .env is not a valid key. Add a real key and rerun.")
        log = add_strong_flags(log, truth_for(lab))  # after the run, so the agent never sees it
        if args.chooser == "llm":
            chooser.book.save(out_dir / f"hypotheses_{run_id}.json")
            (out_dir / f"heldout_predictions_{run_id}.json").write_text(json.dumps({
                "drug_codes": chooser.mask.code if chooser.mask else None,
                "predictions": [p.model_dump() for p in preds] if preds is not None else None}, indent=1))
            print(f"LLM cost: ${chooser.llm.total_cost:.2f}")
        out = out_dir / f"run_log_{method}_{args.outcome}_seed{seed}.csv"
        log.to_csv(out, index=False)
        print(f"seed {seed}: {len(log)} experiments, strong (primary) {int(log['is_strong_joint_within_line'].sum())}"
              f" -> {out}")


if __name__ == "__main__":
    main()
