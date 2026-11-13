"""The shortlist the agent chooses from (plan 8.3 step 1), shared with the shortlist-random control.

With a response model: the top ~90% by mean + kappa*std (the BO score) plus the most uncertain ~10%,
ordered by BO score, with pred_mean / pred_std columns. So the shortlist's first k rows are exactly
BO's batch (same model, same kappa): the "model-only shortlist" control from plan 9.2 equals BO.
Without a model: a random sample. Tissue is added when known (public metadata)."""
import numpy as np


def make_shortlist(candidates, history, rng, model=None, target="synergy", n=50,
                   explore_frac=0.1, kappa=1.0, tissue=None):
    n = min(n, len(candidates))
    if model is None:
        short = candidates.iloc[rng.choice(len(candidates), size=n, replace=False)].reset_index(drop=True)
    else:
        mean, std = model.fit(history, target).predict(candidates)
        order = np.argsort(-(mean + kappa * std), kind="stable")
        n_explore = max(1, round(n * explore_frac))
        top = order[:n - n_explore]
        rest = np.setdiff1d(np.arange(len(candidates)), top)
        unsure = rest[np.argsort(-std[rest], kind="stable")[:n_explore]]
        keep = np.concatenate([top, unsure])
        short = candidates.iloc[keep].reset_index(drop=True)
        short["pred_mean"], short["pred_std"] = mean[keep].round(2), std[keep].round(2)
    if tissue:
        short.insert(4, "tissue", short["cell_line"].map(tissue).fillna("unknown"))
    return short
