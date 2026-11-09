"""Offline tests for agent/prompts.py: a fake Claude returns scripted replies."""
import json
from types import SimpleNamespace

import pandas as pd
import pytest

from agent import prompts
from agent.prompts import LLM, Hypothesis, critique, hypothesize, select

SHORTLIST = pd.DataFrame({
    "exp_id": [f"E{i}" for i in range(12)],
    "drug_a": ["ABT-888"] * 6 + ["LAPATINIB"] * 6,
    "drug_b": ["CARBOPLATIN"] * 6 + ["ERLOTINIB"] * 6,
    "cell_line": ["LINE_A", "LINE_B", "LINE_C"] * 4,
})
ANNOTATIONS = {"ABT-888": {"drug_class": "PARP inhibitor", "targets": "PARP1; PARP2"}}
EVIDENCE = {"ABT-888 + CARBOPLATIN": {"drug_a": [{"source_id": "PMID:1", "year": "2020",
            "title": "PARP trapping", "abstract": "Veliparib traps PARP."}], "drug_b": [], "pair": []}}
HISTORY = pd.DataFrame({"drug_a": ["ABT-888"], "drug_b": ["CARBOPLATIN"], "cell_line": ["LINE_A"],
                        "synergy": [12.0], "inhibition": [40.0]})


def reply(payload, stop="end_turn", model=prompts.MODEL):
    text = payload if isinstance(payload, str) else json.dumps(payload)
    return SimpleNamespace(stop_reason=stop, model=model, content=[SimpleNamespace(type="text", text=text)],
                           usage=SimpleNamespace(input_tokens=1000, output_tokens=500,
                                                 cache_read_input_tokens=0, cache_creation_input_tokens=0))


class FakeClaude:
    def __init__(self, *replies):
        self.replies, self.requests = list(replies), []
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.requests.append(kwargs)
        return self.replies.pop(0)


@pytest.fixture(autouse=True)
def tmp_logs(monkeypatch, tmp_path):
    monkeypatch.setattr(prompts, "LOG_DIR", tmp_path)


def hyp(id="H1", **kw):
    return {"id": id, "statement": "PARP inhibition plus platinum is synergistic in HR-deficient lines",
            "drugs": ["ABT-888", "CARBOPLATIN"], "level": "mechanistic", "predicted_responders": ["LINE_A"],
            "rationale": "PARP trapping adds to platinum DNA damage", "evidence_ids": ["PMID:1"], **kw}


def run_hypothesize(*replies):
    fake = FakeClaude(*replies)
    llm = LLM("test", client=fake)
    return hypothesize(llm, SHORTLIST, ANNOTATIONS, EVIDENCE, HISTORY, []), fake, llm


def test_valid_hypotheses_pass_and_are_logged():
    out, fake, llm = run_hypothesize(reply({"hypotheses": [hyp()]}))
    assert [h.id for h in out] == ["H1"]
    log = [json.loads(l) for l in llm.log_path.read_text().splitlines()]
    assert len(log) == 1 and log[0]["problems"] == [] and log[0]["cost_usd"] == pytest.approx(0.014)


def test_request_uses_fixed_model_schema_and_fallback():
    _, fake, _ = run_hypothesize(reply({"hypotheses": [hyp()]}))
    req = fake.requests[0]
    assert req["model"] == "claude-opus-5-5" and req["output_config"]["effort"] == "high"
    assert req["output_config"]["format"]["schema"]["additionalProperties"] is False
    assert req["fallbacks"] == "default" and req["betas"] == ["server-side-fallback-2026-07-01"]


@pytest.mark.parametrize("bad, problem", [
    (hyp(evidence_ids=["PMID:999"]), "not provided"),       # invented citation
    (hyp(drugs=["ASPIRIN"]), "not in shortlist"),
    (hyp(predicted_responders=["LINE_Z"]), "unknown cell lines"),
    (hyp(predicted_responders=[]), "must name predicted responder"),
])
def test_bad_content_gets_one_retry_with_feedback(bad, problem):
    out, fake, _ = run_hypothesize(reply({"hypotheses": [bad]}), reply({"hypotheses": [hyp()]}))
    assert [h.id for h in out] == ["H1"]
    assert problem in fake.requests[1]["messages"][0]["content"]


def test_two_failures_return_none_and_both_are_logged():
    out, _, llm = run_hypothesize(reply("not json"), reply({"wrong": "shape"}))
    assert out is None
    assert len(llm.log_path.read_text().splitlines()) == 2


def test_refusal_counts_as_failure():
    out, _, _ = run_hypothesize(reply("", stop="refusal"), reply({"hypotheses": [hyp()]}))
    assert [h.id for h in out] == ["H1"]


def test_critique_needs_one_verdict_per_hypothesis():
    h = [Hypothesis(**hyp("H1")), Hypothesis(**hyp("H2"))]
    v = {"id": "H1", "verdict": "keep", "revised_statement": "", "reason": "ok", "evidence_ids": []}
    fake = FakeClaude(reply({"verdicts": [v]}), reply({"verdicts": [v, {**v, "id": "H2", "verdict": "drop"}]}))
    out = critique(LLM("test", client=fake), h, EVIDENCE, HISTORY)
    assert [x.verdict for x in out] == ["keep", "drop"]
    assert "exactly one verdict" in fake.requests[1]["messages"][0]["content"]


def pick(e, h="H1"):
    return {"exp_id": e, "hypothesis_id": h, "level": "mechanistic", "reason": "tests H1"}


def test_select_rejects_repeats_and_ids_outside_shortlist():
    bad = {"picks": [pick("E0")] * 2 + [pick("E99")] + [pick(f"E{i}") for i in range(1, 8)]}
    good = {"picks": [pick(f"E{i}") for i in range(10)]}
    fake = FakeClaude(reply(bad), reply(good))
    out = select(LLM("test", client=fake), SHORTLIST, [Hypothesis(**hyp())], HISTORY, k=10)
    assert [p.exp_id for p in out] == [f"E{i}" for i in range(10)]
    feedback = fake.requests[1]["messages"][0]["content"]
    assert "repeated" in feedback and "E99" in feedback


def test_select_falls_back_to_shortlist_order():
    fake = FakeClaude(reply("garbage"), reply("garbage"))
    out = select(LLM("test", client=fake), SHORTLIST, [], HISTORY, k=10)
    assert [p.exp_id for p in out] == list(SHORTLIST["exp_id"][:10])
    assert all("fell back" in p.reason for p in out)


def test_prompt_shows_only_returned_results():
    _, fake, _ = run_hypothesize(reply({"hypotheses": [hyp()]}))
    prompt = fake.requests[0]["messages"][0]["content"]
    assert "1 experiments run so far" in prompt
    assert "is_strong" not in prompt and "threshold" not in prompt.lower()
