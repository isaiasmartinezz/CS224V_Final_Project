"""Held-out mechanism test (plan Section 9.3). Evaluation only; exploratory (10 held-out lines).

After a run, the agent predicts which held-out lines should respond to each mechanistic hypothesis
(agent.prompts.predict_heldout; it sees only line names and genetics). Scoring per hypothesis:
  1. covered pairs = drug pairs the hypothesis covers (agent.hypotheses.covers)
  2. each held-out line's response = mean, over covered pairs, of the pair's percentile *within that line*
     (target score: synergy, inhibition, or joint = the smaller of the two percentiles)
  3. responders = lines whose response is above the median line (top half)
  4. precision of the predicted responders vs the base rate, and the response gap
     (mean response of predicted lines minus the rest)
Overall: mean precision vs mean base rate, and a permutation test (random predictions of the same
sizes, 10,000 draws) for the mean gap.

Usage: python -m backup_lab.mechanism_test   (scores every heldout_predictions_*.json in the results dir)"""
import argparse
import json

import numpy as np
import pandas as pd

from agent.hypotheses import covers
from agent.lab_source import SOURCES, get_source, make_lab, results_dir


def line_percentiles(heldout, target):
    pct = heldout.groupby("cell_line")[["synergy", "inhibition"]].rank(pct=True)
    if target == "joint":
        return np.minimum(pct["synergy"], pct["inhibition"])
    return pct[target]


def score_one(drugs, predicted, heldout, pct):
    mask = [covers(drugs, a, b) for a, b in zip(heldout["drug_a"], heldout["drug_b"])]
    if not any(mask):
        return None
    resp = pct[mask].groupby(heldout.loc[mask, "cell_line"]).mean()
    responders = set(resp[resp > resp.median()].index)
    pred = [l for l in predicted if l in resp.index]
    if not pred:
        return {"n_predicted": 0, "n_lines": len(resp)}
    rest = resp.drop(pred)
    return {"n_predicted": len(pred), "n_lines": len(resp),
            "precision": len(set(pred) & responders) / len(pred),
            "base_rate": len(responders) / len(resp),
            "gap": float(resp[pred].mean() - rest.mean()) if len(rest) else 0.0,
            "_resp": resp}


def permutation_p(scored, n=10_000, seed=0):
    """P(mean gap of random predictions of the same sizes >= observed mean gap)."""
    rng = np.random.default_rng(seed)
    observed = np.mean([s["gap"] for s in scored])
    sims = np.zeros(n)
    for s in scored:
        r = s["_resp"].to_numpy()
        k = s["n_predicted"]
        for i in range(n):
            pick = rng.choice(len(r), size=k, replace=False)
            rest = np.delete(r, pick)
            sims[i] += r[pick].mean() - (rest.mean() if len(rest) else r[pick].mean())
    sims /= len(scored)
    return float((sims >= observed).mean())


def score_run(hyp_path, pred_path, heldout, target):
    hyps = {h["id"]: h for h in json.loads(hyp_path.read_text())["hypotheses"]}
    pred = json.loads(pred_path.read_text())
    unmask = {c: d for d, c in (pred.get("drug_codes") or {}).items()}
    pct = line_percentiles(heldout, target)
    rows, scored = [], []
    for p in pred.get("predictions") or []:
        h = hyps.get(p["hypothesis_id"])
        if h is None:
            continue
        drugs = [unmask.get(d, d) for d in h["drugs"]]
        s = score_one(drugs, p["predicted_responders"], heldout, pct)
        if s is None:
            continue
        rows.append({"hypothesis_id": h["id"], "drugs": "+".join(drugs), "status": h.get("status"),
                     **{k: v for k, v in s.items() if not k.startswith("_")}})
        if s["n_predicted"]:
            scored.append(s)
    return pd.DataFrame(rows), scored


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lab", choices=SOURCES, default=None)
    args = ap.parse_args()
    source = get_source(args.lab)
    out_dir = results_dir(source)
    heldout = make_lab(source)._heldout_results()
    all_rows, all_scored = [], []
    for pred_path in sorted(out_dir.glob("heldout_predictions_*.json")):
        run_id = pred_path.stem.removeprefix("heldout_predictions_")
        target = next((t for t in ("joint", "synergy", "inhibition") if f"_{t}_seed" in run_id), "joint")
        df, scored = score_run(out_dir / f"hypotheses_{run_id}.json", pred_path, heldout, target)
        all_rows.append(df.assign(run=run_id))
        all_scored += scored
    if not all_rows:
        raise SystemExit(f"no heldout_predictions_*.json in {out_dir} (they come from real agent runs)")
    table = pd.concat(all_rows, ignore_index=True)
    table.to_csv(out_dir / "mechanism_test.csv", index=False)
    if all_scored:
        print(f"{len(all_scored)} scored predictions; mean precision "
              f"{np.mean([s['precision'] for s in all_scored]):.2f} vs base rate "
              f"{np.mean([s['base_rate'] for s in all_scored]):.2f}; mean gap "
              f"{np.mean([s['gap'] for s in all_scored]):+.3f}; permutation p = {permutation_p(all_scored):.3f}")
    print(f"skipped (no predicted responders): {(table['n_predicted'] == 0).sum()}  -> {out_dir / 'mechanism_test.csv'}")


if __name__ == "__main__":
    main()
