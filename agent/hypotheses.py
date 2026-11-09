"""The agent's running list of hypotheses and how results update them.

Status rule (uses only results the lab has returned, never hidden thresholds):
each observed experiment gets its percentile rank among all experiments run so far.
A hypothesis "covers" an experiment when the experiment's drugs fit the hypothesis
(one-drug hypothesis: the drug is in the pair; multi-drug: both drugs are in its set).
  - fewer than MIN_TESTS covered experiments -> "open"
  - mean percentile >= SUPPORT -> "supported";  <= REFUTE -> "refuted";  otherwise "open"
For mechanistic hypotheses we also record responder_gap: mean percentile in predicted
responder lines minus in other lines (positive = the predicted lines did better)."""
import json
from pathlib import Path
from typing import Literal, Optional

import pandas as pd

from agent.prompts import Hypothesis

MIN_TESTS = 2
SUPPORT, REFUTE = 0.65, 0.35


class Tracked(Hypothesis):
    status: Literal["open", "supported", "refuted", "dropped"] = "open"
    round_added: int = 0
    n_tests: int = 0
    score: Optional[float] = None  # mean percentile of covered experiments
    responder_gap: Optional[float] = None


def covers(drugs, drug_a, drug_b):
    d = set(drugs)
    return drug_a in d or drug_b in d if len(d) == 1 else {drug_a, drug_b} <= d


class HypothesisBook:
    def __init__(self):
        self.items = {}  # id -> Tracked
        self.events = []  # every add / critique / status change, for the run record

    def active(self):
        return [h for h in self.items.values() if h.status != "dropped"]

    def add(self, hypotheses, round_num):
        for h in hypotheses or []:
            self.items[h.id] = Tracked(**h.model_dump(), round_added=round_num)
            self.events.append({"round": round_num, "id": h.id, "event": "added", "level": h.level})

    def apply_critique(self, verdicts, round_num):
        for v in verdicts or []:
            h = self.items.get(v.id)
            if h is None:
                continue
            if v.verdict == "drop":
                h.status = "dropped"
            elif v.verdict == "revise":
                h.statement = v.revised_statement
            self.events.append({"round": round_num, "id": v.id, "event": f"critique:{v.verdict}",
                                "reason": v.reason})

    def update(self, history, outcome, round_num):
        """Re-score every active hypothesis against all results seen so far."""
        if history is None or len(history) == 0:
            return
        pct = pd.to_numeric(history[outcome]).rank(pct=True)  # run logs can hold object dtype
        for h in self.active():
            mask = [covers(h.drugs, a, b) for a, b in zip(history["drug_a"], history["drug_b"])]
            covered = pct[mask]
            h.n_tests = len(covered)
            h.score = round(float(covered.mean()), 3) if len(covered) else None
            if h.level == "mechanistic" and len(covered):
                is_resp = history.loc[mask, "cell_line"].isin(h.predicted_responders)
                if is_resp.any() and (~is_resp).any():
                    h.responder_gap = round(float(covered[is_resp.values].mean() - covered[~is_resp.values].mean()), 3)
            new = ("open" if h.n_tests < MIN_TESTS else
                   "supported" if h.score >= SUPPORT else "refuted" if h.score <= REFUTE else "open")
            if new != h.status:
                self.events.append({"round": round_num, "id": h.id, "event": f"status:{h.status}->{new}",
                                    "n_tests": h.n_tests, "score": h.score})
                h.status = new

    def save(self, path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(json.dumps({
            "hypotheses": [h.model_dump() for h in self.items.values()],
            "events": self.events,
        }, indent=1))
