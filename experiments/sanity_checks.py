"""Sanity checks over everything in the results folder (milestones: Sat/Sun checks).

  1. every run log: 250 rows, no exp_id twice, no held-out cell line, every exp_id is a real candidate
  2. all methods share the same first batch for the same seed
  3. replaying every cached PubMed search through agent.retrieval.search returns no excluded paper
     (the cache keeps raw results; the filter runs on the way out, so this checks what the agent sees)
  4. LLM prompts (results/llm_logs, if any): no held-out line names outside the held-out prediction
     step, no evaluation words (is_strong, threshold, cutoff, quantile)

Usage: python experiments/sanity_checks.py   (exit code 1 if anything fails)"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd  # noqa: E402

from agent.lab_source import get_source, make_lab, results_dir  # noqa: E402
from agent.retrieval import is_excluded, load_exclusions, search  # noqa: E402

PATTERN = re.compile(r"run_log_(?P<method>.+)_(?P<target>synergy|inhibition|joint)_seed(?P<seed>\d+)\.csv")
EVAL_WORDS = re.compile(r"is_strong|threshold|cutoff|quantile", re.IGNORECASE)


def main():
    source = get_source()
    lab = make_lab(source)
    out_dir = results_dir(source)
    visible, heldout = set(lab.candidates()["exp_id"]), set(lab._heldout)
    failures, n_logs = [], 0

    first = {}
    for path in sorted(out_dir.rglob("run_log_*.csv")):
        m = PATTERN.fullmatch(path.name)
        if not m:
            continue
        n_logs += 1
        log = pd.read_csv(path)
        name = path.relative_to(out_dir)
        if len(log) != 250:
            failures.append(f"{name}: {len(log)} rows, expected 250")
        if not log["exp_id"].is_unique:
            failures.append(f"{name}: an exp_id was run twice")
        if bad := set(log["cell_line"]) & heldout:
            failures.append(f"{name}: held-out lines in log: {sorted(bad)}")
        if bad := set(log["exp_id"]) - visible:
            failures.append(f"{name}: exp_ids that are not candidates: {sorted(bad)[:3]}")
        batch = tuple(log.loc[log["round"] == 0, "exp_id"])
        first.setdefault(m["seed"], {})[str(name)] = batch
    for seed, batches in first.items():
        if len(set(batches.values())) > 1:
            failures.append(f"seed {seed}: methods do not share the first batch ({len(set(batches.values()))} variants)")

    rules, n_papers, n_raw_excluded = load_exclusions(), 0, 0
    for f in Path("data/cache/pubmed").glob("*.json"):
        cached = json.loads(f.read_text())
        n_raw_excluded += sum(is_excluded(p, rules) for p in cached.get("papers", []))
        returned = search(cached["query"], max_results=max(cached["n"] - 10, 1))  # served from cache
        n_papers += len(returned)
        for paper in returned:
            if is_excluded(paper, rules):
                failures.append(f"search({cached['query'][:40]!r}) returned excluded {paper.get('source_id')}")

    n_calls = 0
    for f in Path("results/llm_logs").glob("*.jsonl") if Path("results/llm_logs").exists() else []:
        for line in f.read_text().splitlines():
            call = json.loads(line)
            n_calls += 1
            prompt = call["prompt"]
            if EVAL_WORDS.search(prompt):
                failures.append(f"{f.name} {call['step']}: evaluation word in prompt")
            if call["step"] != "predict_heldout" and (bad := {l for l in heldout if re.search(rf"\b{re.escape(l)}\b", prompt)}):
                failures.append(f"{f.name} {call['step']}: held-out line names in prompt: {sorted(bad)}")

    print(f"checked {n_logs} run logs; {n_papers} papers returned from cached searches "
          f"({n_raw_excluded} excluded papers sit in the raw cache and were filtered out); {n_calls} LLM calls")
    if failures:
        print("FAILED:\n  " + "\n  ".join(failures))
        sys.exit(1)
    print("all sanity checks passed")


if __name__ == "__main__":
    main()
