"""Hypothesis tracking, explanations, and a full LLM-agent run with a fake Claude (offline)."""
import io
import json
import re
from types import SimpleNamespace

import pandas as pd
import pytest

from agent import prompts
from agent.agent import LLMChooser, run_agent
from agent.explanations import explain
from agent.hypotheses import HypothesisBook
from agent.prompts import LLM, Hypothesis, Pick, Verdict
from agent.stub_lab import StubLab


@pytest.fixture(autouse=True)
def tmp_logs(monkeypatch, tmp_path):
    monkeypatch.setattr(prompts, "LOG_DIR", tmp_path)


def hyp(id, drugs, level="statistical", responders=()):
    return Hypothesis(id=id, statement=f"{id} statement", drugs=list(drugs), level=level,
                      predicted_responders=list(responders), rationale="r", evidence_ids=["PMID:1"])


HISTORY = pd.DataFrame({
    "drug_a":   ["A", "A", "A", "C", "C", "C", "E", "E"],
    "drug_b":   ["B", "B", "B", "D", "D", "D", "F", "F"],
    "cell_line": ["L1", "L2", "L3", "L1", "L2", "L3", "L1", "L2"],
    "synergy":  [9, 8, 7, 1, 2, 3, 5, 4],
})


def test_status_comes_from_percentiles_of_observed_results():
    book = HypothesisBook()
    book.add([hyp("H1", "AB"), hyp("H2", "CD"), hyp("H3", "EF"), hyp("H4", "XY")], round_num=1)
    book.update(HISTORY, "synergy", round_num=2)
    status = {h.id: h.status for h in book.items.values()}
    assert status == {"H1": "supported", "H2": "refuted", "H3": "open", "H4": "open"}
    assert book.items["H4"].n_tests == 0  # never tested stays open


def test_one_drug_hypothesis_covers_any_pair_with_that_drug():
    book = HypothesisBook()
    book.add([hyp("H1", "A")], 1)
    book.update(HISTORY, "synergy", 2)
    assert book.items["H1"].n_tests == 3


def test_mechanistic_responder_gap():
    book = HypothesisBook()
    book.add([hyp("H1", "AB", "mechanistic", ["L1"])], 1)
    book.update(HISTORY, "synergy", 2)
    assert book.items["H1"].responder_gap > 0  # L1 had the best A+B result


def test_critique_drop_and_revise():
    book = HypothesisBook()
    book.add([hyp("H1", "AB"), hyp("H2", "CD")], 1)
    book.apply_critique([
        Verdict(id="H1", verdict="drop", revised_statement="", reason="contradicted", evidence_ids=[]),
        Verdict(id="H2", verdict="revise", revised_statement="better", reason="narrower", evidence_ids=[]),
    ], 1)
    assert book.items["H1"].status == "dropped" and [h.id for h in book.active()] == ["H2"]
    assert book.items["H2"].statement == "better"


def test_mechanistic_explanation_needs_responders():
    book = HypothesisBook()
    book.add([hyp("H1", "AB", "mechanistic", ["L1", "L2"]), hyp("H2", "CD", "statistical")], 1)
    ok = explain(Pick(exp_id="E1", hypothesis_id="H1", level="mechanistic", reason="tests H1"), book)
    assert ok["explanation_level"] == "mechanistic" and "Predicted responders: L1, L2" in ok["explanation_text"]
    down = explain(Pick(exp_id="E2", hypothesis_id="H2", level="mechanistic", reason="x"), book)
    assert down["explanation_level"] == "statistical"
    explore = explain(Pick(exp_id="E3", hypothesis_id="explore", level="mechanistic", reason="x"), book)
    assert explore["explanation_level"] == "statistical" and explore["retrieved_source_ids"] == ""


# ---------- full run with a fake Claude that gives valid answers ----------

def section(prompt, title):
    return prompt.split(f"## {title}\n", 1)[1].split("\n\n## ", 1)[0]


class FakeClaude:
    """Answers each step validly by reading the prompt it receives."""

    def __init__(self):
        self.n, self.prompts = 0, []
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self.create))

    def create(self, **kw):
        prompt = kw["messages"][0]["content"]
        self.prompts.append(prompt)
        step = kw["output_config"]["format"]["schema"]["title"]
        if step == "Hypotheses":
            row = pd.read_csv(io.StringIO(section(prompt, "Shortlist"))).iloc[0]
            self.n += 1
            out = {"hypotheses": [{"id": f"H{self.n}", "statement": "s", "drugs": [row.drug_a, row.drug_b],
                                   "level": "mechanistic", "predicted_responders": [row.cell_line],
                                   "rationale": "r", "evidence_ids": ["PMID:1"]}]}
        elif step == "Critique":
            ids = [h["id"] for h in json.loads(section(prompt, "Hypotheses"))]
            out = {"verdicts": [{"id": i, "verdict": "keep", "revised_statement": "", "reason": "ok",
                                 "evidence_ids": []} for i in ids]}
        else:
            k = int(re.search(r"Choose exactly (\d+)", prompt).group(1))
            ids = pd.read_csv(io.StringIO(section(prompt, "Shortlist")))["exp_id"][:k]
            hyps = json.loads(section(prompt, "Hypotheses"))
            out = {"picks": [{"exp_id": e, "hypothesis_id": hyps[-1]["id"], "level": "mechanistic",
                              "reason": "tests it"} for e in ids]}
        return SimpleNamespace(stop_reason="end_turn", model=prompts.MODEL,
                               content=[SimpleNamespace(type="text", text=json.dumps(out))],
                               usage=SimpleNamespace(input_tokens=10, output_tokens=10,
                                                     cache_read_input_tokens=0, cache_creation_input_tokens=0))


def test_full_llm_run_logs_hypotheses_and_explanations():
    fake = FakeClaude()
    evidence = lambda a, b: {"drug_a": [{"source_id": "PMID:1", "year": "2020", "title": "t", "abstract": "a"}],
                             "drug_b": [], "pair": []}
    chooser = LLMChooser("t", llm=LLM("t", client=fake), retrieve=evidence)
    log = run_agent(StubLab(), seed=0, chooser=chooser)

    assert len(log) == 250 and log["exp_id"].is_unique
    agent_rows = log[log["round"] > 0]
    assert agent_rows["hypothesis_id"].str.startswith("H").all()
    assert (agent_rows["explanation_level"] == "mechanistic").all()
    assert agent_rows["explanation_text"].str.contains("Predicted responders").all()
    assert agent_rows["retrieved_source_ids"].eq("PMID:1").all()
    assert len(chooser.llm.log_path.read_text().splitlines()) == 3 * 24  # 3 steps x rounds 1-24
    assert any(e["event"].startswith("status:") for e in chooser.book.events)
    assert not any("is_strong" in p or "threshold" in p.lower() for p in fake.prompts)
