"""Smoke test: run hypothesize -> critique -> select once on a hand-made example with real
retrieval and the real Claude API. Costs a few cents; needs ANTHROPIC_API_KEY in .env.

Usage: python experiments/try_prompts.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import anthropic  # noqa: E402
import pandas as pd  # noqa: E402

from agent.prompts import LLM, critique, hypothesize, select  # noqa: E402
from agent.retrieval import evidence_for_pair  # noqa: E402
from agent.stub_lab import StubLab  # noqa: E402

PAIRS = [("ABT-888", "CARBOPLATIN"), ("LAPATINIB", "ERLOTINIB"), ("MRK-003", "PACLITAXEL")]


def main():
    lab = StubLab()  # fake cell lines and scores; only the drug names are real
    cands = lab.candidates()
    keep = pd.Series(False, index=cands.index)
    for a, b in PAIRS:
        keep |= (cands["drug_a"] == min(a, b)) & (cands["drug_b"] == max(a, b))
    shortlist = cands[keep].groupby(["drug_a", "drug_b"]).head(5).reset_index(drop=True)
    history = shortlist.head(3).merge(lab.run(shortlist["exp_id"][:3]), on="exp_id")
    shortlist = shortlist.iloc[3:]

    ann = pd.read_csv("data/drug_annotations.csv", dtype=str).set_index("drug").to_dict("index")
    evidence = {f"{a} + {b}": evidence_for_pair(a, b, per_query=3) for a, b in PAIRS}

    llm = LLM("smoke_test")
    try:
        hyps = hypothesize(llm, shortlist, ann, evidence, history, [])
    except anthropic.AuthenticationError:
        sys.exit("ANTHROPIC_API_KEY in .env is not a valid key. Add a real key and rerun.")
    print("\nHYPOTHESES:" if hyps else "\nHYPOTHESIZE FAILED twice")
    for h in hyps or []:
        print(f"  {h.id} [{h.level}] {h.statement}\n     responders={h.predicted_responders} cites={h.evidence_ids}")
    if hyps:
        verdicts = critique(llm, hyps, evidence, history)
        print("\nCRITIQUE:" if verdicts else "\nCRITIQUE FAILED twice")
        for v in verdicts or []:
            print(f"  {v.id}: {v.verdict} - {v.reason}")
    picks = select(llm, shortlist, hyps or [], history, k=5)
    print("\nPICKS:")
    for p in picks:
        print(f"  {p.exp_id} -> {p.hypothesis_id} [{p.level}] {p.reason}")
    print(f"\nTotal cost: ${llm.total_cost:.3f}  (log: {llm.log_path})")


if __name__ == "__main__":
    main()
