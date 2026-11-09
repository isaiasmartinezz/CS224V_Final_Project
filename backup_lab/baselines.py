"""Baselines (backup copy of Ryan's lab/baselines.py, plan Section 8.2).

Each baseline is a "chooser" with the same signature as the agent's:
    chooser(candidates, history, k, rng) -> (exp_ids, explanations)
so every method runs through agent.agent.run_agent and gets the same shared first batch.
  random       pick k untested experiments at random
  uncertainty  pick the k the response model is least sure about (highest std)
  bo           Bayesian optimization, upper confidence bound: highest mean + KAPPA * std"""
import numpy as np

from agent.agent import random_chooser
from backup_lab.response_model import ResponseModel

KAPPA = 1.0  # UCB exploration weight; see notes/decision_log.md


def ucb(mean, std, kappa=KAPPA):
    return mean + kappa * std


class ModelChooser:
    def __init__(self, strategy, outcome="synergy", tissue=None, kappa=KAPPA, seed=0):
        assert strategy in ("uncertainty", "bo")
        self.strategy, self.outcome, self.tissue, self.kappa, self.seed = strategy, outcome, tissue, kappa, seed
        self.model = None

    def __call__(self, candidates, history, k, rng):
        if self.model is None:  # candidates on the first call hold every visible cell line
            self.model = ResponseModel(candidates["cell_line"].unique(), tissue=self.tissue, seed=self.seed)
        mean, std = self.model.fit(history, self.outcome).predict(candidates)
        score = std if self.strategy == "uncertainty" else ucb(mean, std, self.kappa)
        top = np.argsort(-score, kind="stable")[:k]
        notes = [{"explanation_level": "none",
                  "explanation_text": f"{self.strategy}: pred_mean={mean[i]:.2f} pred_std={std[i]:.2f}"}
                 for i in top]
        return list(candidates["exp_id"].iloc[top]), notes


def make_baseline(name, outcome="synergy", tissue=None, seed=0):
    if name == "random":
        return random_chooser
    return ModelChooser(name, outcome=outcome, tissue=tissue, seed=seed)
