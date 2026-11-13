"""What counts as a "strong" combination (plan Section 6, updated with research-team feedback, Nov 2026).
Evaluation only: never shown to any method during a run. Computed on all non-held-out experiments.

Definitions (primary = joint_within_line, decided with the research team; joint = secondary):
  synergy / inhibition   top `quantile` (default 5%) of that one score
  joint                  synergy in its top SYN_TOP (10%) AND inhibition (CSS) above a cutoff tuned so
                         about TARGET (5%) of experiments qualify. Two cutoffs, not a sum: the scores
                         are on different scales (team suggestion: "top 10% synergy and top 25% CSS")
  joint_within_line      same rule on each experiment's percentile *within its own cell line*, so a
                         method can't score well just by picking generally drug-sensitive lines"""
import numpy as np
import pandas as pd

OUTCOMES = ("synergy", "inhibition")
DEFINITIONS = ("joint_within_line", "joint", "synergy", "inhibition")
PRIMARY = "joint_within_line"  # team decision (Nov 2026); "joint" is the secondary result
SYN_TOP, TARGET = 0.10, 0.05


def strong_thresholds(truth, quantiles=(0.95, 0.99)):
    """{(outcome, quantile): cutoff} for the single-score definitions."""
    return {(o, q): float(truth[o].quantile(q)) for o in OUTCOMES for q in quantiles}


def _joint(syn, inh, syn_top=SYN_TOP, target=TARGET):
    """Fix synergy at its top `syn_top`; pick the inhibition cutoff whose joint fraction is closest to target."""
    syn_ok = syn >= syn.quantile(1 - syn_top)
    passing = np.sort(inh[syn_ok].to_numpy())  # inhibition values among synergy-passing rows
    candidates = np.unique(passing)[::-1]
    # fraction qualifying if cutoff = candidates[i] (counts ties, which within-line percentiles have)
    fracs = (len(passing) - np.searchsorted(passing, candidates, side="left")) / len(syn)
    i = int(np.argmin(np.abs(fracs - target)))
    inh_cut = float(candidates[i])
    labels = syn_ok & (inh >= inh_cut)
    info = {"synergy_cutoff": float(syn.quantile(1 - syn_top)), "inhibition_cutoff": inh_cut,
            "inhibition_top_pct": round(float((inh >= inh_cut).mean()) * 100, 1),
            "fraction_strong": round(float(labels.mean()), 4)}
    return labels, info


def within_line_percentiles(truth):
    return truth.groupby("cell_line")[list(OUTCOMES)].rank(pct=True)


def strong_labels(truth, definition=PRIMARY, quantile=0.95):
    """Boolean Series (index = exp_id) saying which experiments are strong, plus a dict of cutoffs."""
    if definition in OUTCOMES:
        cut = float(truth[definition].quantile(quantile))
        labels = truth[definition] >= cut
        return labels, {f"{definition}_cutoff": cut, "fraction_strong": round(float(labels.mean()), 4)}
    if definition == "joint":
        return _joint(truth["synergy"], truth["inhibition"])
    if definition == "joint_within_line":
        pct = within_line_percentiles(truth)
        labels, info = _joint(pct["synergy"], pct["inhibition"])
        return labels, {f"{k} (within-line percentile)" if "cutoff" in k else k: v for k, v in info.items()}
    raise ValueError(f"definition must be one of {DEFINITIONS}")


def flag_strong(log, truth, definition=PRIMARY, quantile=0.95):
    labels, _ = strong_labels(truth, definition, quantile)
    out = log.copy()
    out[f"is_strong_{definition}"] = out["exp_id"].map(labels).fillna(False).astype(bool)
    return out


def strong_by_line(truth, definitions=DEFINITIONS):
    """How the strong set is spread over cell lines: count per line under each definition."""
    cols = {d: strong_labels(truth, d)[0] for d in definitions}
    return pd.DataFrame(cols).join(truth["cell_line"]).groupby("cell_line").sum().astype(int)
