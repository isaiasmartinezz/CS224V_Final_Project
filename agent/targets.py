"""What a method tries to maximize, computed only from results the lab has already returned.

  synergy / inhibition   the raw score
  joint                  "good on both, for this cell line": each score has its cell line's observed
                         mean removed (shrunk toward the overall mean when a line has few results),
                         is standardized, and the joint value is the smaller of the two.
                         Mirrors the evaluation definition (both scores high, ranked within line)
                         without ever using hidden results or the evaluation cutoffs."""
import numpy as np
import pandas as pd

TARGETS = ("synergy", "inhibition", "joint")
SHRINK = 2  # a line's mean counts like SHRINK extra results at the overall mean
# (with ~8 results per line, ~80% of a line's general sensitivity is removed)
DESCRIBE = {
    "synergy": "synergy",
    "inhibition": "growth inhibition",
    "joint": "joint score (both synergy and growth inhibition high relative to other experiments "
             "in the same cell line; the smaller of the two standardized, line-adjusted scores)",
}


def line_adjusted(y, lines, shrink=SHRINK):
    y = pd.to_numeric(y).astype(float)
    g = y.groupby(lines)
    n, m = g.transform("size"), g.transform("mean")
    resid = y - (n * m + shrink * y.mean()) / (n + shrink)
    sd = resid.std()
    return (resid - resid.mean()) / (sd if sd and np.isfinite(sd) else 1.0)


def joint_score(history):
    syn = line_adjusted(history["synergy"], history["cell_line"])
    inh = line_adjusted(history["inhibition"], history["cell_line"])
    return np.minimum(syn, inh)


def with_target(history, target):
    """Copy of history with a `joint` column added when needed."""
    if target != "joint" or history is None or len(history) == 0:
        return history
    out = history.copy()
    out["joint"] = joint_score(out).round(4) if len(out) > 1 else 0.0
    return out
