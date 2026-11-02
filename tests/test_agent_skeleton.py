import numpy as np
import pytest

from agent.agent import run_agent
from agent.stand_in_lab import StandInLab


def test_full_run_respects_lab_rules():
    lab = StandInLab()
    log = run_agent(lab, seed=0)
    assert len(log) == 250 and log["round"].nunique() == 25
    assert log["exp_id"].is_unique
    assert lab.budget_remaining() == 0
    assert not log["cell_line"].isin(lab._heldout).any()
    assert log[["synergy", "inhibition"]].notna().all().all()


def test_lab_rejects_repeats_and_overspending():
    lab = StandInLab(budget=5)
    ids = list(lab.candidates()["exp_id"][:6])
    lab.run(ids[:3])
    with pytest.raises(ValueError):
        lab.run(ids[:1])
    with pytest.raises(ValueError):
        lab.run(ids[3:6])


def test_same_first_batch_for_any_chooser():
    def first_k(cands, history, k, rng):
        return list(cands["exp_id"][:k]), [{}] * k

    a = run_agent(StandInLab(), seed=3)
    b = run_agent(StandInLab(), seed=3, chooser=first_k)
    assert set(a[a["round"] == 0]["exp_id"]) == set(b[b["round"] == 0]["exp_id"])
    assert set(a[a["round"] == 1]["exp_id"]) != set(b[b["round"] == 1]["exp_id"])


def test_agent_cannot_see_heldout_candidates():
    lab = StandInLab()
    assert not lab.candidates()["cell_line"].isin(lab._heldout).any()
