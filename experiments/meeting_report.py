"""Figures + one markdown summary of every result so far, for building slides elsewhere.

Inputs: results/backup/ run logs (joint target), hypotheses_*.json, heldout_predictions_*.json,
results/llm_logs/*.jsonl, model_check.csv. Outputs:
  results/backup/figures/ladder_seed0.png      strong combinations found at 250, the four-step ladder
  results/backup/figures/discovery_seed0.png   discovery curves, all methods, seed 0
  notes/meeting_2026-11-13_results.md          numbers, figures, examples (paste into a slide-making chat)

Seed 0 is the fair same-seed comparison (the agent ran one seed); baselines also show 5-seed mean ± sd.

Usage: python experiments/meeting_report.py"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import matplotlib  # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from agent.lab_source import make_lab, results_dir, truth_for  # noqa: E402
from backup_lab.familiarity import pair_group  # noqa: E402
from backup_lab.mechanism_test import permutation_p, score_run  # noqa: E402
from backup_lab.thresholds import strong_labels  # noqa: E402

OUT = results_dir("backup")
FIG = OUT / "figures"
MD = Path("notes/meeting_2026-11-13_results.md")
# dataviz reference palette, categorical slots 1-6 in fixed order (light surface)
SURFACE, INK, INK2 = "#fcfcfb", "#0b0b0b", "#52514e"
METHODS = [  # (file method name, display label, color)
    ("random", "Random", "#2a78d6"),
    ("uncertainty", "Uncertainty sampling", "#eb6834"),
    ("shortlist_random", "Random from shortlist", "#1baf7a"),
    ("bo", "Statistics (BO)", "#eda100"),
    ("agent_no_literature", "Statistics + LLM", "#e87ba4"),
    ("agent", "Statistics + LLM + literature", "#008300"),
]
LADDER = ["random", "bo", "agent_no_literature", "agent"]


def load(method, seed):
    p = OUT / f"run_log_{method}_joint_seed{seed}.csv"
    return pd.read_csv(p) if p.exists() else None


def style(ax):
    ax.set_facecolor(SURFACE)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color("#c9c8c3")
    ax.tick_params(colors=INK2, labelsize=10)
    ax.grid(axis="y", color="#e6e5e0", linewidth=0.8)
    ax.set_axisbelow(True)


def fmt_p(p):
    return "< 0.001" if p < 0.001 else f"= {p:.3f}"


def llm_stats(run_id):
    p = Path("results/llm_logs") / f"{run_id}.jsonl"
    if not p.exists():
        return None
    calls = [json.loads(l) for l in p.read_text().splitlines()]
    return {"calls": len(calls), "cost": sum(c["cost_usd"] for c in calls),
            "input_tokens": sum(c["input_tokens"] for c in calls),
            "output_tokens": sum(c["output_tokens"] for c in calls),
            "retries": sum(c["attempt"] == 2 for c in calls),
            "failed": sum(bool(c["problems"]) for c in calls),
            "models": sorted({c["model_served"] for c in calls})}


def main():
    truth = truth_for(make_lab("backup"))
    labels, info = strong_labels(truth, "joint_within_line")
    sec_labels, _ = strong_labels(truth, "joint")
    rate = float(labels.mean())
    fam = dict(pd.read_csv("data/drug_familiarity.csv")[["drug", "group"]].values)
    FIG.mkdir(parents=True, exist_ok=True)

    rows, curves = [], {}
    for m, name, color in METHODS:
        per_seed = {s: load(m, s) for s in range(5)}
        found = {s: int(l["exp_id"].map(labels).fillna(False).sum()) for s, l in per_seed.items() if l is not None}
        sec = {s: int(l["exp_id"].map(sec_labels).fillna(False).sum()) for s, l in per_seed.items() if l is not None}
        if 0 in found:
            curves[m] = np.cumsum(per_seed[0]["exp_id"].map(labels).fillna(False).to_numpy(bool))
        vals = np.array(list(found.values()))
        rows.append({"method": name, "key": m, "seed0": found.get(0), "secondary_seed0": sec.get(0),
                     "seeds": len(vals), "mean": vals.mean() if len(vals) else None,
                     "sd": vals.std() if len(vals) else None})
    table = pd.DataFrame(rows)

    # ---- ladder bar chart (seed 0, with 5-seed mean ± sd where available) ----
    fig, ax = plt.subplots(figsize=(8, 4.5), facecolor=SURFACE)
    style(ax)
    lad = table.set_index("key").loc[[k for k in LADDER if k in table["key"].values]]
    colors = {m: c for m, _, c in METHODS}
    x = np.arange(len(lad))
    ax.bar(x, lad["seed0"].fillna(0), width=0.55, color=[colors[k] for k in lad.index],
           edgecolor=SURFACE, linewidth=2)
    for i, (k, r) in enumerate(lad.iterrows()):
        if pd.notna(r["seed0"]):
            ax.text(i, r["seed0"] + 1, f"{int(r['seed0'])}", ha="center", va="bottom", color=INK, fontsize=12)
        if r["seeds"] and r["seeds"] > 1:
            ax.errorbar(i + 0.33, r["mean"], yerr=r["sd"], fmt="o", ms=5, color=INK2, capsize=3, lw=1)
    ax.axhline(250 * rate, color=INK2, ls=":", lw=1.2)
    ax.text(len(lad) - 0.5, 250 * rate + 1, "chance", color=INK2, fontsize=9, ha="right")
    ax.set_xticks(x, [r["method"].replace(" + ", " +\n") for _, r in lad.iterrows()], color=INK)
    ax.set_ylabel("Strong combinations found in 250 experiments", color=INK2)
    ax.set_title("Each step adds one ingredient (seed 0; dot = 5-seed mean ± sd)", color=INK, loc="left", fontsize=12)
    fig.tight_layout()
    fig.savefig(FIG / "ladder_seed0.png", dpi=200, facecolor=SURFACE)
    plt.close(fig)

    # ---- discovery curves, seed 0 ----
    fig, ax = plt.subplots(figsize=(8, 4.8), facecolor=SURFACE)
    style(ax)
    xs = np.arange(1, 251)
    for m, name, color in METHODS:
        if m in curves:
            ax.plot(xs[:len(curves[m])], curves[m], color=color, lw=2.2 if m in ("bo", "agent") else 1.6, label=name)
            if m in ("bo", "agent"):
                ax.text(len(curves[m]) + 3, curves[m][-1], name, color=INK, fontsize=9, va="center")
    ax.plot(xs, xs * rate, color=INK2, ls=":", lw=1.2, label="Expected by chance")
    ax.set_xlim(0, 300)
    ax.set_xlabel("Experiments run", color=INK2)
    ax.set_ylabel("Strong combinations found", color=INK2)
    ax.set_title("Discovery curves (seed 0, strong = both scores high within cell line)", color=INK, loc="left", fontsize=12)
    ax.legend(frameon=False, fontsize=9, loc="upper left", labelcolor=INK)
    fig.tight_layout()
    fig.savefig(FIG / "discovery_seed0.png", dpi=200, facecolor=SURFACE)
    plt.close(fig)

    # ---- agent details ----
    agent_sections = []
    for m, name in [("agent", "Statistics + LLM + literature"), ("agent_no_literature", "Statistics + LLM (no literature)")]:
        run_id = f"backup_{m}_joint_seed0"
        log = load(m, 0)
        if log is None:
            agent_sections.append(f"### {name}\nNot run yet.\n")
            continue
        st = llm_stats(run_id)
        picks = log[log["round"] > 0]
        levels = picks["explanation_level"].value_counts().to_dict()
        fallback = int(picks["explanation_text"].str.contains("fell back", na=False).sum())
        hyp_path = OUT / f"hypotheses_{run_id}.json"
        hyps = json.loads(hyp_path.read_text())["hypotheses"] if hyp_path.exists() else []
        status = pd.Series([h["status"] for h in hyps]).value_counts().to_dict() if hyps else {}
        groups = log["exp_id"].map(dict(zip(truth.index, [pair_group(a, b, fam) for a, b in
                                                        zip(truth["drug_a"], truth["drug_b"])])))
        strong = log["exp_id"].map(labels).fillna(False).astype(bool)
        by_group = {g: f"{int((strong & (groups == g)).sum())} strong / {int((groups == g).sum())} picked"
                    for g in ("famous", "mixed", "obscure")}
        mech = ""
        pred_path = OUT / f"heldout_predictions_{run_id}.json"
        if pred_path.exists() and hyp_path.exists():
            df, scored = score_run(hyp_path, pred_path, make_lab("backup")._heldout_results(), "joint")
            if scored:
                mech = (f"- Held-out mechanism test: {len(scored)} mechanistic hypotheses scored on the 10 never-tested "
                        f"cell lines. Mean precision {np.mean([s['precision'] for s in scored]):.2f} vs "
                        f"{np.mean([s['base_rate'] for s in scored]):.2f} by guessing; mean response gap "
                        f"{np.mean([s['gap'] for s in scored]):+.3f}; permutation p {fmt_p(permutation_p(scored))} "
                        f"(exploratory: 10 lines, one run; hypotheses overlap, so they are not independent "
                        f"and this p-value is optimistic).\n")
            else:
                mech = "- Held-out mechanism test: no scorable predictions.\n"
        examples = []
        mechs = picks[picks["explanation_level"] == "mechanistic"]
        for _, r in pd.concat([mechs[mechs["exp_id"].map(labels).fillna(False)], mechs]).drop_duplicates("exp_id").head(3).iterrows():
            examples.append(f"  - **{r.drug_a} + {r.drug_b} in {r.cell_line}** (round {r['round']}; "
                            f"{'strong' if labels.get(r.exp_id, False) else 'not strong'}): {r.explanation_text} "
                            f"[sources: {r.retrieved_source_ids if isinstance(r.retrieved_source_ids, str) and r.retrieved_source_ids else 'none'}]")
        agent_sections.append(
            f"### {name}\n"
            f"- Cost: ${st['cost']:.2f} for {st['calls']} LLM calls ({st['input_tokens']:,} input / "
            f"{st['output_tokens']:,} output tokens); retries {st['retries']}; model(s) {', '.join(st['models'])}\n"
            f"- Explanation levels of its {len(picks)} picks: {levels}; picks that fell back to BO order: {fallback}\n"
            f"- Hypotheses proposed: {len(hyps)}; final status: {status}\n"
            f"- By drug familiarity: {by_group}\n" + mech +
            ("- Example explanations:\n" + "\n".join(examples) + "\n" if examples else ""))

    def fmt(r):
        spread = f"{r['mean']:.1f} ± {r['sd']:.1f} ({r['seeds']} seeds)" if r["seeds"] and r["seeds"] > 1 else "1 seed"
        return f"| {r['method']} | {'' if pd.isna(r['seed0']) else int(r['seed0'])} | {spread} |"

    v = table.set_index("key")
    context = (
        f"How to read this: the agent chooses from the model's 50-candidate shortlist, so the fair bar is "
        f"**random picks from that same shortlist**. Across 5 seeds that control nearly matches BO "
        f"({v.loc['shortlist_random', 'mean']:.1f} vs {v.loc['bo', 'mean']:.1f}): the shortlist does most of the work. "
        f"On seed 0 specifically, the shortlist control found {int(v.loc['shortlist_random', 'seed0'])} "
        f"(a high draw) and BO {int(v.loc['bo', 'seed0'])} (a low draw). "
        f"So on this seed the LLM without literature ({int(v.loc['agent_no_literature', 'seed0'])}) beat every "
        f"baseline, while the LLM with literature ({int(v.loc['agent', 'seed0'])}) roughly tied the shortlist "
        f"control. With one run per agent arm and seed-to-seed sd of 8-13 for the baselines, these are "
        f"promising but not yet conclusive; more seeds are needed before claiming the LLM adds value, or that "
        f"literature hurts.")
    total = sum((llm_stats(f"backup_{m}_joint_seed0") or {"cost": 0})["cost"] for m in ("agent", "agent_no_literature"))
    smoke = (llm_stats("smoke_test") or {"cost": 0})["cost"]
    mc = pd.read_csv(OUT / "model_check.csv")
    mc250 = mc[(mc.n_train == 250) & (mc.features == "with genetics")].set_index("outcome")
    md = f"""# Cancer-Combo-Agent: results for the Nov 13 meeting

Generated by `experiments/meeting_report.py`. Figures are in `results/backup/figures/`.

## The question
Can an LLM agent that reads the literature find strong cancer drug combinations in fewer experiments
than statistical methods? The O'Neil 2016 screen (38 drugs, 39 cancer cell lines, 22,737 experiments)
is used as a simulated lab: results stay hidden until a method "runs" an experiment. Each method gets
250 experiments (about 1.5% of the 16,907 it may choose from), in batches of 10. 10 cell lines are held
out entirely for the mechanism test.

## What counts as "strong" (agreed with the research team)
Top 10% Loewe synergy AND CSS (growth inhibition) above a cutoff, both ranked *within each cell line*,
tuned so {rate:.1%} of experiments qualify. Within-line ranking stops a method from winning just by
picking generally drug-sensitive cell lines (with CSS alone, 5 lines hold 57% of top results).
Expected by chance in 250 picks: {250 * rate:.1f}.

## The four-step ladder (main result)
Each step adds one ingredient. Same seed (0) and same first batch for every method.

| Method | Strong found (seed 0) | Across seeds |
|---|---|---|
""" + "\n".join(fmt(r) for _, r in table.iterrows()) + f"""

![Ladder](../results/backup/figures/ladder_seed0.png)
![Discovery curves](../results/backup/figures/discovery_seed0.png)

{context}

## The agent runs (real LLM)
Model: Claude Sonnet 5.5, effort medium, literature trimmed to 3 drug pairs x 2 papers per search per
round (budget: whole study under $30). Total API spend so far: ${total + smoke:.2f}
(both runs ${total:.2f} + smoke test ${smoke:.2f}).

""" + "\n".join(agent_sections) + f"""

## Supporting results
- Response model (random forest, 250 training experiments): rank accuracy {mc250.loc['synergy', 'spearman']:.2f}
  (synergy) / {mc250.loc['inhibition', 'spearman']:.2f} (inhibition); its uncertainty is calibrated
  ({mc250.loc['synergy', 'within_1sd']:.0%} of values within 1 sd) but barely tracks errors for inhibition,
  which is why uncertainty sampling does poorly.
- Data checks: drug names matched by PubChem ID (38/38); cell-line genetics from Sanger Cell Model
  Passports (34/39 lines with mutation data; unknowns left unknown, never guessed).
- Leakage controls: the agent never sees hidden results, held-out lines, or the "strong" cutoffs;
  literature search excludes the O'Neil paper and synergy-prediction ML papers. All sanity checks pass.
- Built and ready but not yet run: no-critique and masked-drug-names ablations; more seeds.

## Limitations to say out loud
- One run per agent arm: suggestive, not conclusive.
- Cost grew during each run because the hypothesis list was never pruned (100+ hypotheses by the end;
  prompts grew from ~12k to ~43k tokens, and critique re-judged all of them every round). Runs cost
  $6-8 each; capping active hypotheses should bring that to ~$2-3, making 5 seeds of both arms ~$20-30.
- The mechanism test uses only 10 held-out lines: exploratory.
- PubMed abstracts stand in for SHELDON (access pending).

## Next steps
1. Cap the active hypothesis list (cost fix), then 5 seeds of both agent arms; then the no-critique
   and masked-names ablations.
2. Read explanations by hand for grounding; tune prompts if needed.
3. SHELDON if access arrives; paper draft and final slides.
"""
    MD.write_text(md)
    print(table.to_string(index=False))
    print(f"-> {MD}, {FIG / 'ladder_seed0.png'}, {FIG / 'discovery_seed0.png'}")


if __name__ == "__main__":
    main()
