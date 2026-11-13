"""Joint target, controls, ablations, cell-line genetics, held-out prediction, mechanism scoring, familiarity."""
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from agent import prompts
from agent.agent import DrugMask, LLMChooser, initial_batch, run_agent
from agent.prompts import LLM, Hypothesis, predict_heldout
from agent.stub_lab import StubLab
from agent.targets import joint_score, with_target
from backup_lab.baselines import ModelChooser
from backup_lab.familiarity import pair_group
from backup_lab.mechanism_test import line_percentiles, score_one
from backup_lab.response_model import ResponseModel
from tests.test_agent_llm import FakeClaude

ANN = pd.read_csv("data/drug_annotations.csv", dtype=str).set_index("drug").to_dict("index")
EVIDENCE = lambda a, b: {"drug_a": [{"source_id": "PMID:1", "year": "2020", "title": f"{a} in cancer",
                                     "abstract": f"{a} and {b} were studied."}], "drug_b": [], "pair": []}


@pytest.fixture(autouse=True)
def tmp_logs(monkeypatch, tmp_path):
    monkeypatch.setattr(prompts, "LOG_DIR", tmp_path)


def history(lab, n=60, seed=0):
    ids = initial_batch(lab.candidates(), seed, n)
    return lab.candidates().set_index("exp_id").loc[ids].reset_index().merge(lab.run(ids), on="exp_id")


# ---------- joint target ----------

def test_joint_removes_most_of_a_line_effect():
    """Line effect sized like the real CSS data (cell line explains ~13% of variance; sd ~22),
    8 results per line (about what a 250-experiment run sees), averaged over 200 draws."""
    rng = np.random.default_rng(0)
    n, gaps_joint, gaps_raw = 8, [], []
    for _ in range(200):
        h = pd.DataFrame({"cell_line": ["A"] * n + ["B"] * n, "synergy": rng.normal(0, 15, 2 * n),
                          "inhibition": np.r_[np.full(n, 58.0), np.full(n, 42.0)] + rng.normal(0, 20, 2 * n)})
        z = lambda c: (h[c] - h[c].mean()) / h[c].std()
        j, raw = joint_score(h), np.minimum(z("synergy"), z("inhibition"))
        gaps_joint.append(j[:n].mean() - j[n:].mean())
        gaps_raw.append(raw[:n].mean() - raw[n:].mean())
    assert np.mean(gaps_joint) < 0.4 * np.mean(gaps_raw)


def test_joint_needs_both_scores():
    h = pd.DataFrame({"cell_line": ["A"] * 6, "synergy": [9, 9, 0, 0, 5, 5], "inhibition": [9, 0, 9, 0, 5, 5]})
    j = joint_score(h)
    assert j[0] > j[4] > max(j[1], j[2]) > j[3] - 1e-9  # high on both beats medium beats high on one
    assert "joint" in with_target(h, "joint") and "joint" not in with_target(h, "synergy")


# ---------- controls ----------

def test_bo_batch_equals_top_of_agent_shortlist():
    lab = StubLab()
    hist, cands = history(lab), lab.candidates()
    lines = cands["cell_line"].unique()
    bo_ids, _ = ModelChooser("bo", outcome="joint", seed=0)(cands, hist, 10, np.random.default_rng(0))
    agent = LLMChooser("t", outcome="joint", llm=object(), retrieve=EVIDENCE, model=ResponseModel(lines, seed=0))
    short = agent.shortlist(cands, hist, np.random.default_rng(0))
    assert list(short["exp_id"][:10]) == bo_ids  # "model-only shortlist" control == BO


def test_shortlist_random_picks_inside_the_shortlist():
    lab = StubLab()
    hist, cands = history(lab), lab.candidates()
    picks, _ = ModelChooser("shortlist_random", outcome="joint")(cands, hist, 10, np.random.default_rng(1))
    agent = LLMChooser("t", outcome="joint", llm=object(), retrieve=EVIDENCE,
                       model=ResponseModel(cands["cell_line"].unique(), seed=0))
    assert set(picks) <= set(agent.shortlist(cands, hist, np.random.default_rng(1))["exp_id"])
    assert len(set(picks)) == 10


# ---------- ablations ----------

def run_fake(ablation, outcome="joint", rounds_budget=60):
    fake = FakeClaude()
    lab = StubLab(budget=rounds_budget)
    chooser = LLMChooser("t", outcome=outcome, llm=LLM("t", client=fake), retrieve=EVIDENCE, ablation=ablation)
    log = run_agent(lab, seed=0, chooser=chooser)
    return fake, chooser, log


def test_masked_names_hide_every_drug_name_from_the_llm():
    fake, chooser, log = run_fake("masked_names")
    names = [d for d in ANN] + [a["search_name"] for a in ANN.values() if a["search_name"] != "unknown"]
    for p in fake.prompts:
        assert not [n for n in names if len(n) > 3 and n.lower() in p.lower()], "a real drug name leaked"
    assert "Drug 0" in fake.prompts[0]
    assert len(log) == 60 and log["exp_id"].is_unique


def test_mask_replaces_names_inside_abstracts():
    m = DrugMask(ANN)
    ev = m.evidence({"ABT-888 + CARBOPLATIN": EVIDENCE("ABT-888", "carboplatin")})
    text = json.dumps(ev)
    assert "ABT-888" not in text and "carboplatin" not in text.lower() and m.code["ABT-888"] in text


def test_no_critique_and_no_literature():
    fake, _, _ = run_fake("no_critique")
    assert not any("Challenge each hypothesis" in p for p in fake.prompts)
    fake, _, _ = run_fake("no_literature")
    assert all("(no literature retrieved)" in p for p in fake.prompts if "## Literature" in p)


def test_joint_target_is_explained_and_shown_to_the_llm():
    fake, _, _ = run_fake("none", outcome="joint")
    later = [p for p in fake.prompts if "experiments run so far" in p]
    assert later and "joint score" in fake.prompts[0] and ",joint" in later[0]


# ---------- held-out prediction (names + genetics only) ----------

def test_predict_heldout_only_names_untested_lines():
    llm = LLM("t", client=FakeClaude())
    hyps = [Hypothesis(id="H1", statement="s", drugs=["ABT-888", "CARBOPLATIN"], level="mechanistic",
                       predicted_responders=["X"], rationale="r", evidence_ids=[]),
            Hypothesis(id="H2", statement="s", drugs=["A"], level="statistical", predicted_responders=[],
                       rationale="r", evidence_ids=[])]
    preds = predict_heldout(llm, hyps, {"HL1": "BRCA1 mut", "HL2": "none", "HL3": "KRAS G12D"})
    assert [p.hypothesis_id for p in preds] == ["H1"]  # mechanistic only
    assert set(preds[0].predicted_responders) <= {"HL1", "HL2", "HL3"}


# ---------- mechanism scoring ----------

def test_mechanism_score_rewards_correct_predictions():
    rng = np.random.default_rng(0)
    rows = []
    for line, boost in [("L1", 3), ("L2", 3), ("L3", 0), ("L4", 0)]:
        for a, b in [("A", "B"), ("C", "D"), ("E", "F"), ("G", "H")]:
            s = rng.normal() + (boost if (a, b) == ("A", "B") else 0)
            rows.append({"drug_a": a, "drug_b": b, "cell_line": line, "synergy": s, "inhibition": s})
    held = pd.DataFrame(rows)
    pct = line_percentiles(held, "joint")
    good = score_one(["A", "B"], ["L1", "L2"], held, pct)
    bad = score_one(["A", "B"], ["L3", "L4"], held, pct)
    assert good["precision"] == 1.0 and bad["precision"] == 0.0 and good["gap"] > 0 > bad["gap"]
    assert score_one(["X", "Y"], ["L1"], held, pct) is None  # hypothesis covers nothing held out


# ---------- genetics and familiarity ----------

def test_response_model_uses_line_genetics():
    lab = StubLab()
    hist, cands = history(lab), lab.candidates()
    lines = sorted(cands["cell_line"].unique())
    feats = {"line": pd.DataFrame({"mut_TP53": [i % 2 for i in range(len(lines))], "has_genetics": 1}, index=lines),
             "target_expr": pd.DataFrame({d: np.linspace(0, 5, len(lines)) for d in ANN}, index=lines)}
    plain = ResponseModel(lines, n_trees=10)
    rich = ResponseModel(lines, n_trees=10, line_features=feats)
    assert rich.featurize(cands.head(3)).shape[1] == plain.featurize(cands.head(3)).shape[1] + 2 + 2
    mean, std = rich.fit(hist, "synergy").predict(cands)
    assert len(mean) == len(cands) and np.isfinite(mean).all()


def test_pair_groups():
    fam = {"A": "famous", "B": "famous", "C": "obscure"}
    assert [pair_group("A", "B", fam), pair_group("A", "C", fam), pair_group("C", "C", fam)] == \
           ["famous", "mixed", "obscure"]


@pytest.mark.skipif(not Path("data/processed/backup/cell_line_summaries.csv").exists(), reason="build features first")
def test_unknown_genetics_stay_unknown():
    s = pd.read_csv("data/processed/backup/cell_line_summaries.csv").set_index("cell_line")["summary"]
    assert "unknown" in s["COLO320DM"]
    assert "BRCA1: unknown" in s["UWB1289+BRCA1"] and "BRCA1" not in s["UWB1289+BRCA1"].split(";")[2]
