"""Strong-combination thresholds (plan Section 6): top 5% (main) and top 1% (sensitivity check)
of all non-held-out experiments, computed separately for each outcome.
Evaluation only: never shown to any method during a run."""
OUTCOMES = ("synergy", "inhibition")


def strong_thresholds(truth, quantiles=(0.95, 0.99)):
    """{(outcome, quantile): score cutoff}. An experiment is strong if its score >= the cutoff."""
    return {(o, q): float(truth[o].quantile(q)) for o in OUTCOMES for q in quantiles}


def flag_strong(log, truth, quantile=0.95):
    cut = strong_thresholds(truth, (quantile,))
    out = log.copy()
    for o in OUTCOMES:
        out[f"is_strong_{o}"] = out[o].astype(float) >= cut[(o, quantile)]
    return out
