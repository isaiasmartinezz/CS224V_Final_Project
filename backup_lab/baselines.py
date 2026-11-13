"""Baselines and controls (plan Sections 8.2 and 9.2).

Each is a "chooser" with the same signature as the agent's:
    chooser(candidates, history, k, rng) -> (exp_ids, explanations)
so every method runs through agent.agent.run_agent and gets the same shared first batch.
  random            pick k untested experiments at random
  uncertainty       pick the k the response model is least sure about (highest std)
  bo                Bayesian optimization, upper confidence bound: highest mean + KAPPA * std.
                    Also the "model-only shortlist" control: the agent's shortlist is ordered by the
                    same score, so BO's batch = the shortlist's top k.
  shortlist_random  k at random from the agent's 50-candidate shortlist: does the LLM choose
                    better than chance *within* the list it is given?
Target (what the model learns): synergy | inhibition | joint (agent/targets.py)."""
import numpy as np

from agent.agent import random_chooser
from agent.shortlist import make_shortlist
from agent.targets import with_target
from backup_lab.response_model import ResponseModel

KAPPA = 1.0  # UCB exploration weight; see notes/decision_log.md
METHODS = ("random", "uncertainty", "bo", "shortlist_random")


def ucb(mean, std, kappa=KAPPA):
    return mean + kappa * std


class ModelChooser:
    def __init__(self, strategy, outcome="synergy", tissue=None, kappa=KAPPA, seed=0, line_features=None):
        assert strategy in ("uncertainty", "bo", "shortlist_random")
        self.strategy, self.outcome, self.tissue, self.kappa, self.seed = strategy, outcome, tissue, kappa, seed
        self.line_features = line_features
        self.model = None

    def __call__(self, candidates, history, k, rng):
        if self.model is None:  # candidates on the first call hold every visible cell line
            self.model = ResponseModel(candidates["cell_line"].unique(), tissue=self.tissue, seed=self.seed,
                                       line_features=self.line_features)
        hist = with_target(history, self.outcome)
        if self.strategy == "shortlist_random":
            short = make_shortlist(candidates, hist, rng, model=self.model, target=self.outcome, kappa=self.kappa)
            idx = rng.choice(len(short), size=k, replace=False)
            return list(short["exp_id"].iloc[idx]), [
                {"explanation_level": "none", "explanation_text": "random pick from the 50-candidate shortlist"}] * k
        mean, std = self.model.fit(hist, self.outcome).predict(candidates)
        score = std if self.strategy == "uncertainty" else ucb(mean, std, self.kappa)
        top = np.argsort(-score, kind="stable")[:k]
        notes = [{"explanation_level": "none",
                  "explanation_text": f"{self.strategy}: pred_mean={mean[i]:.2f} pred_std={std[i]:.2f}"}
                 for i in top]
        return list(candidates["exp_id"].iloc[top]), notes


def make_baseline(name, outcome="synergy", tissue=None, seed=0, kappa=KAPPA, line_features=None):
    if name == "random":
        return random_chooser
    return ModelChooser(name, outcome=outcome, tissue=tissue, seed=seed, kappa=kappa, line_features=line_features)
