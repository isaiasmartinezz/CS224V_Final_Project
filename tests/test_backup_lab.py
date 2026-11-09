"""Backup copy of Ryan's lab: switch, cleaning, held-out choice, SimLab rules, model, baselines, agent shortlist."""
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from agent import lab_source
from agent.agent import LLMChooser, initial_batch, run_agent
from agent.stub_lab import StubLab
from backup_lab.baselines import ModelChooser
from backup_lab.clean_oneil import choose_heldout, clean
from backup_lab.response_model import ResponseModel
from backup_lab.sim_lab import SimLab
from backup_lab.thresholds import strong_thresholds

REAL = Path("data/processed/backup/oneil_clean.csv")
needs_data = pytest.mark.skipif(not REAL.exists(), reason="run backup_lab.fetch_oneil and clean_oneil first")


# ---------- the switch ----------

def test_switch_reads_env_and_cli(monkeypatch):
    monkeypatch.setenv("LAB_SOURCE", "ryan")
    assert lab_source.get_source() == "ryan"
    assert lab_source.get_source("stub") == "stub"  # --lab beats .env
    monkeypatch.setenv("LAB_SOURCE", "nonsense")
    with pytest.raises(SystemExit):
        lab_source.get_source()


def test_ryan_source_fails_clearly_without_his_code():
    if Path("lab/sim_lab.py").exists():
        pytest.skip("Ryan's lab exists")
    with pytest.raises(SystemExit, match="LAB_SOURCE=backup"):
        lab_source.make_lab("ryan")


# ---------- cleaning ----------

def test_clean_maps_names_sorts_pairs_and_averages_replicates():
    raw = pd.DataFrame({
        "drug_row": ["Veliparib", "Carboplatinum", "Veliparib"],
        "drug_col": ["Carboplatinum", "Veliparib", "paclitaxel"],
        "cell_line_name": ["A375", "A375", "A375"], "tissue_name": ["skin"] * 3,
        "synergy_zip": [2.0, 4.0, 1.0], "synergy_loewe": [0.0] * 3, "synergy_bliss": [0.0] * 3,
        "synergy_hsa": [0.0] * 3, "css_ri": [10.0, 20.0, 5.0]})
    out, dropped = clean(raw)
    assert dropped == 0 and len(out) == 2
    first = out.iloc[0]
    assert (first.drug_a, first.drug_b) == ("ABT-888", "CARBOPLATIN")  # mapped, then sorted
    assert first.synergy == 3.0 and first.inhibition == 15.0 and first.n_replicates == 2


def test_clean_refuses_unknown_drug_names():
    raw = pd.DataFrame({"drug_row": ["Mystery"], "drug_col": ["paclitaxel"], "cell_line_name": ["X"],
                        "tissue_name": ["t"], "synergy_zip": [1.0], "synergy_loewe": [1.0],
                        "synergy_bliss": [1.0], "synergy_hsa": [1.0], "css_ri": [1.0]})
    with pytest.raises(ValueError, match="Mystery"):
        clean(raw)


def test_heldout_is_spread_across_tissues_and_fixed():
    lines = pd.DataFrame({"cell_line": [f"L{i}" for i in range(39)],
                          "tissue": ["a"] * 6 + ["b"] * 8 + ["c"] * 8 + ["d"] * 9 + ["e"] * 2 + ["f"] * 6})
    picks = choose_heldout(lines)
    assert len(picks) == 10 and picks == choose_heldout(lines)
    per_tissue = lines.set_index("cell_line").loc[picks, "tissue"].value_counts()
    assert per_tissue.max() <= 3 and per_tissue.size >= 5


# ---------- SimLab on the real data ----------

@needs_data
def test_simlab_rules_and_no_heldout_leak():
    lab = SimLab()
    cands = lab.candidates()
    assert not set(cands["cell_line"]) & set(lab._heldout)
    assert list(cands.columns) == ["exp_id", "drug_a", "drug_b", "cell_line"]  # no results, no tissue
    first = list(cands["exp_id"][:10])
    res = lab.run(first)
    assert list(res.columns) == ["exp_id", "synergy", "inhibition"] and lab.budget_remaining() == 240
    assert not set(first) & set(lab.candidates()["exp_id"])
    with pytest.raises(ValueError, match="already run"):
        lab.run(first[:1])
    held_id = lab._heldout_results().index[0]
    with pytest.raises(ValueError, match="held-out"):
        lab.run([held_id])
    with pytest.raises(ValueError, match="over budget"):
        lab.run(list(lab.candidates()["exp_id"][:241]))


@needs_data
def test_thresholds_are_top_5_and_1_percent():
    truth = SimLab()._all_results()
    t = strong_thresholds(truth)
    assert abs((truth["synergy"] >= t[("synergy", 0.95)]).mean() - 0.05) < 0.002
    assert t[("inhibition", 0.99)] > t[("inhibition", 0.95)]


# ---------- response model and baselines (fake lab: fast) ----------

def small_history(lab, n=40, seed=0):
    ids = initial_batch(lab.candidates(), seed, n)
    return lab.candidates().set_index("exp_id").loc[ids].reset_index().merge(lab.run(ids), on="exp_id")


def test_response_model_gives_mean_and_std_for_every_candidate():
    lab = StubLab()
    hist = small_history(lab)
    cands = lab.candidates()
    model = ResponseModel(cands["cell_line"].unique(), n_trees=20)
    mean, std = model.fit(hist, "synergy").predict(cands)
    assert mean.shape == std.shape == (len(cands),) and (std >= 0).all() and std.max() > 0


def test_model_baselines_pick_k_new_experiments():
    lab = StubLab()
    hist = small_history(lab)
    cands = lab.candidates()
    for strategy in ("uncertainty", "bo"):
        picks, notes = ModelChooser(strategy)(cands, hist, 10, np.random.default_rng(0))
        assert len(set(picks)) == 10 and set(picks) <= set(cands["exp_id"]) and len(notes) == 10


def test_baseline_shares_first_batch_with_agent():
    a = run_agent(StubLab(), seed=3)
    b = run_agent(StubLab(), seed=3, chooser=ModelChooser("bo"))
    assert list(a[a["round"] == 0]["exp_id"]) == list(b[b["round"] == 0]["exp_id"])
    assert b["exp_id"].is_unique and len(b) == 250


# ---------- the agent's shortlist uses the model when one is given ----------

def test_agent_shortlist_uses_model_scores_and_tissue():
    lab = StubLab()
    hist = small_history(lab)
    cands = lab.candidates()
    model = ResponseModel(cands["cell_line"].unique(), n_trees=20)
    tissue = {l: "skin" for l in cands["cell_line"].unique()}
    chooser = LLMChooser("t", llm=object(), retrieve=lambda a, b: {}, model=model, tissue=tissue)
    short = chooser.shortlist(cands, hist, np.random.default_rng(0))
    assert len(short) == 50 and short["exp_id"].is_unique
    assert {"pred_mean", "pred_std", "tissue"} <= set(short.columns)
    top = short.iloc[:45]
    ucb = (top["pred_mean"] + top["pred_std"]).to_numpy()
    assert (np.diff(ucb) <= 0.011).all()  # ordered by BO score (kappa=1), allowing for 2-dp rounding


@needs_data
def test_full_llm_agent_on_real_data_with_fake_claude(monkeypatch, tmp_path):
    from agent import prompts
    from agent.prompts import LLM
    from tests.test_agent_llm import FakeClaude

    monkeypatch.setattr(prompts, "LOG_DIR", tmp_path)
    lab = SimLab()
    lines = lab.candidates()["cell_line"].unique()
    chooser = LLMChooser("t", llm=LLM("t", client=FakeClaude()), retrieve=lambda a, b: {
        "drug_a": [{"source_id": "PMID:1", "year": "2020", "title": "t", "abstract": "a"}], "drug_b": [], "pair": []},
        model=ResponseModel(lines, n_trees=20), tissue=lab_source.cell_line_tissue("backup"))
    log = run_agent(lab, seed=0, chooser=chooser)
    assert len(log) == 250 and log["exp_id"].is_unique
    assert not set(log["cell_line"]) & set(lab._heldout)
    assert log.loc[log["round"] > 0, "explanation_text"].str.contains("Predicted responders").all()
