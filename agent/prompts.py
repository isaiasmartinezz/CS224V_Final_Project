"""LLM steps of the agent: hypothesize, critique, select.

Each step sends one request with a fixed JSON output shape (structured outputs), then checks
the content in code (cited sources were actually provided, drugs and cell lines exist, picks
come from the shortlist). A bad answer gets one retry with the problems listed; if it fails
again, hypothesize/critique return None and select falls back to the response model's ranking.

Every call is appended to results/llm_logs/<run_id>.jsonl with tokens and estimated cost.
The LLM never sees hidden results or "strong" thresholds: only the shortlist, annotations,
retrieved evidence, and results the lab has already returned."""
import json
import time
from pathlib import Path
from typing import Literal

import anthropic
from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, ValidationError

load_dotenv()

# One fixed model for all agent runs (plan Section 12; see notes/decision_log.md)
MODEL = "claude-opus-5-5"
EFFORT = "high"  # reasoning-heavy; Opus 5.5 defaults to "medium" if unset
MAX_TOKENS = 16000
# Opus 5.5 list prices, USD per token. A fallback-served call is priced approximately.
PRICE = {"input": 4e-6, "output": 20e-6, "cache_read": 0.2e-6, "cache_write": 5e-6}
LOG_DIR = Path("results/llm_logs")
ABSTRACT_CHARS = 700  # enough for the key finding; keeps prompts affordable

Level = Literal["mechanistic", "cross_cancer", "statistical"]


# ---------- output shapes ----------

class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Hypothesis(Strict):
    id: str
    statement: str
    drugs: list[str]
    level: Level
    predicted_responders: list[str]  # cell lines; required for mechanistic hypotheses
    rationale: str
    evidence_ids: list[str]


class Hypotheses(Strict):
    hypotheses: list[Hypothesis]


class Verdict(Strict):
    id: str
    verdict: Literal["keep", "revise", "drop"]
    revised_statement: str  # empty unless verdict is "revise"
    reason: str
    evidence_ids: list[str]


class Critique(Strict):
    verdicts: list[Verdict]


class Pick(Strict):
    exp_id: str
    hypothesis_id: str  # a hypothesis id, or "explore"
    level: Level
    reason: str


class Selection(Strict):
    picks: list[Pick]


class HeldoutPrediction(Strict):
    hypothesis_id: str
    predicted_responders: list[str]  # held-out cell lines expected to respond
    reason: str


class HeldoutPredictions(Strict):
    predictions: list[HeldoutPrediction]


# ---------- prompts ----------

SYSTEM = """You are a cancer pharmacologist helping choose drug-combination experiments in a \
screening lab. Each experiment tests one drug pair in one cancer cell line and returns a \
synergy score (higher = drugs work better together than expected) and a growth-inhibition score.

Ground every claim in the material provided: drug annotations, literature excerpts (cite them \
by their IDs, e.g. PMID:12345), and results the lab has already returned. Only cite IDs that \
appear in the provided evidence. If a claim rests on general pharmacology rather than a \
provided source, say so in the rationale and leave it uncited. Prefer specific, testable \
mechanisms over vague ones, and say plainly when evidence is thin."""

HYPOTHESIZE_TASK = """Propose up to {max_h} hypotheses about which drug pairs in the shortlist \
will show high {outcome}, and why. Use the cell lines' genetics where given.

For each hypothesis:
- id: "H<number>", continuing after existing ids
- level: "mechanistic" (a specific pathway in these cells), "cross_cancer" (worked in other \
tumor types), or "statistical" (similar drugs behaved this way in results so far)
- predicted_responders: for mechanistic hypotheses, the cell lines from the shortlist that \
should respond, chosen for a stated reason. Empty for other levels.
- drugs: names exactly as written in the shortlist."""

CRITIQUE_TASK = """Challenge each hypothesis below against the evidence and the results so far. \
Look for: claims the cited sources do not support, results that contradict it, and mechanisms \
that do not apply to the predicted cell lines. Give exactly one verdict per hypothesis: \
"keep", "revise" (write the improved statement), or "drop"."""

SELECT_TASK = """Choose exactly {k} experiments from the shortlist (by exp_id) for the next \
batch. Balance testing the most promising hypotheses against experiments that would tell \
competing hypotheses apart; a few "explore" picks for untested drug classes are fine. Each \
pick names the hypothesis it tests (or "explore"), the explanation level, and a one-sentence \
reason."""


HELDOUT_TASK = """These cell lines were never tested in this screen. For each mechanistic \
hypothesis below, predict which of these cell lines should respond (show high {outcome} for the \
drug pairs the hypothesis covers), using each line's genetics and the hypothesis's mechanism. \
Give exactly one prediction per hypothesis; an empty list means no line should respond. \
Explain the genetic reason in one sentence."""


def _describe(outcome):
    from agent.targets import DESCRIBE
    return DESCRIBE.get(outcome, outcome)


def _fmt_lines(line_info):
    return "\n".join(f"- {l}: {s}" for l, s in sorted(line_info.items())) or "(no genetics available)"


def _fmt_annotations(annotations, drugs):
    lines = []
    for d in sorted(drugs):
        a = annotations.get(d, {})
        lines.append(f"- {d}: {a.get('drug_class', 'unknown')}; targets: {a.get('targets', 'unknown')}")
    return "\n".join(lines)


def _fmt_evidence(evidence):
    """evidence: {"DRUG_A + DRUG_B": evidence_for_pair(...) output}."""
    blocks = []
    for pair, parts in evidence.items():
        blocks.append(f"### {pair}")
        for part, papers in parts.items():
            for p in papers:
                abstract = p["abstract"][:ABSTRACT_CHARS] + ("..." if len(p["abstract"]) > ABSTRACT_CHARS else "")
                blocks.append(f"[{p['source_id']}] ({part}, {p['year']}) {p['title']}\n{abstract}")
    return "\n\n".join(blocks) or "(no literature retrieved)"


def _fmt_shortlist(shortlist):
    cols = [c for c in ["exp_id", "drug_a", "drug_b", "cell_line", "tissue", "pred_mean", "pred_std"]
            if c in shortlist.columns]
    return shortlist[cols].to_csv(index=False)


def _fmt_history(history, outcome, n=15):
    """Results already returned by the lab: best and worst so far, never thresholds."""
    if history is None or len(history) == 0:
        return "(no experiments run yet)"
    h = history.sort_values(outcome, ascending=False)
    cols = ["drug_a", "drug_b", "cell_line", "synergy", "inhibition"] + (
        [outcome] if outcome not in ("synergy", "inhibition") else [])
    return (f"{len(history)} experiments run so far.\nHighest {outcome}:\n{h.head(n)[cols].to_csv(index=False)}"
            f"\nLowest {outcome}:\n{h.tail(5)[cols].to_csv(index=False)}")


def _fmt_hypotheses(hyps):
    return json.dumps([h.model_dump() if isinstance(h, BaseModel) else h for h in hyps], indent=1) if hyps else "(none yet)"


# ---------- the call: structured output, checks, one retry, logging ----------

class LLM:
    def __init__(self, run_id, client=None):
        self.client = client or anthropic.Anthropic()
        self.log_path = LOG_DIR / f"{run_id}.jsonl"
        self.total_cost = 0.0

    def call(self, step, user, schema, check):
        """Returns a validated `schema` instance, or None after two failed attempts.
        `check(parsed)` returns a list of problems that the schema alone cannot catch."""
        feedback = ""
        for attempt in (1, 2):
            content = user + (f"\n\nYour previous answer had these problems; fix them:\n{feedback}" if feedback else "")
            # create() + our own validation (not parse()), so failed attempts are still logged
            response = self.client.beta.messages.create(
                model=MODEL,
                max_tokens=MAX_TOKENS,
                thinking={"type": "adaptive"},
                output_config={"effort": EFFORT,
                               "format": {"type": "json_schema", "schema": anthropic.transform_schema(schema)}},
                # If a safety classifier declines, the API reruns on its recommended fallback
                # model; response.model in the log shows which model actually answered.
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
                system=SYSTEM,
                messages=[{"role": "user", "content": content}],
            )
            parsed, problems = None, []
            if response.stop_reason in ("refusal", "max_tokens"):
                problems = [f"stopped early: {response.stop_reason}"]
            else:
                text = next((b.text for b in response.content if b.type == "text"), "")
                try:
                    parsed = schema.model_validate_json(text)
                    problems = check(parsed)
                except ValidationError as e:  # malformed JSON or wrong shape
                    parsed, problems = None, [f"invalid output: {e}"]
            self._log(step, attempt, content, response, problems)
            if parsed is not None and not problems:
                return parsed
            feedback = "\n".join(f"- {p}" for p in problems)
        return None

    def _log(self, step, attempt, content, response, problems):
        u = response.usage
        cost = (u.input_tokens * PRICE["input"] + u.output_tokens * PRICE["output"]
                + (u.cache_read_input_tokens or 0) * PRICE["cache_read"]
                + (u.cache_creation_input_tokens or 0) * PRICE["cache_write"])
        self.total_cost += cost
        text = next((b.text for b in response.content if b.type == "text"), "")
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        with self.log_path.open("a") as f:
            f.write(json.dumps({
                "time": time.strftime("%Y-%m-%dT%H:%M:%S"), "step": step, "attempt": attempt,
                "model_requested": MODEL, "model_served": response.model, "effort": EFFORT,
                "stop_reason": response.stop_reason, "problems": problems,
                "input_tokens": u.input_tokens, "output_tokens": u.output_tokens,
                "cache_read_tokens": u.cache_read_input_tokens or 0, "cost_usd": round(cost, 5),
                "system": SYSTEM, "prompt": content, "response": text,
            }) + "\n")


# ---------- the three steps ----------

def _source_ids(evidence):
    return {p["source_id"] for parts in evidence.values() for papers in parts.values() for p in papers}


def hypothesize(llm, shortlist, annotations, evidence, history, hypotheses, outcome="synergy", max_h=6,
                line_info=None):
    drugs = set(shortlist["drug_a"]) | set(shortlist["drug_b"])
    lines, ids = set(shortlist["cell_line"]), _source_ids(evidence)
    taken = {h.id for h in hypotheses}
    user = "\n\n".join([
        HYPOTHESIZE_TASK.format(max_h=max_h, outcome=_describe(outcome)),
        f"## Drug annotations\n{_fmt_annotations(annotations, drugs)}",
        f"## Shortlist\n{_fmt_shortlist(shortlist)}",
        f"## Cell lines\n{_fmt_lines(line_info or {})}",
        f"## Results so far\n{_fmt_history(history, outcome)}",
        f"## Existing hypotheses\n{_fmt_hypotheses(hypotheses)}",
        f"## Literature\n{_fmt_evidence(evidence)}",
    ])

    def check(out):
        problems = []
        if not 1 <= len(out.hypotheses) <= max_h:
            problems.append(f"give between 1 and {max_h} hypotheses, not {len(out.hypotheses)}")
        seen = set()
        for h in out.hypotheses:
            if h.id in seen or h.id in taken:
                problems.append(f"{h.id}: id already used")
            seen.add(h.id)
            if bad := set(h.drugs) - drugs:
                problems.append(f"{h.id}: drugs not in shortlist: {sorted(bad)}")
            if bad := set(h.evidence_ids) - ids:
                problems.append(f"{h.id}: cites sources that were not provided: {sorted(bad)}")
            if bad := set(h.predicted_responders) - lines:
                problems.append(f"{h.id}: unknown cell lines: {sorted(bad)}")
            if h.level == "mechanistic" and not h.predicted_responders:
                problems.append(f"{h.id}: mechanistic hypotheses must name predicted responder cell lines")
        return problems

    out = llm.call("hypothesize", user, Hypotheses, check)
    return out.hypotheses if out else None


def critique(llm, hypotheses, evidence, history, outcome="synergy", line_info=None):
    ids, want = _source_ids(evidence), {h.id for h in hypotheses}
    user = "\n\n".join([
        CRITIQUE_TASK,
        f"## Hypotheses\n{_fmt_hypotheses(hypotheses)}",
        f"## Cell lines\n{_fmt_lines(line_info or {})}",
        f"## Results so far\n{_fmt_history(history, outcome)}",
        f"## Literature\n{_fmt_evidence(evidence)}",
    ])

    def check(out):
        got = [v.id for v in out.verdicts]
        problems = []
        if sorted(got) != sorted(want):
            problems.append(f"give exactly one verdict for each of {sorted(want)}; got {got}")
        for v in out.verdicts:
            if v.verdict == "revise" and not v.revised_statement.strip():
                problems.append(f"{v.id}: 'revise' needs a revised_statement")
            if bad := set(v.evidence_ids) - ids:
                problems.append(f"{v.id}: cites sources that were not provided: {sorted(bad)}")
        return problems

    out = llm.call("critique", user, Critique, check)
    return out.verdicts if out else None


def select(llm, shortlist, hypotheses, history, k=10, outcome="synergy"):
    """Always returns k picks: the LLM's if valid, otherwise the shortlist's top k
    (the shortlist is ordered by the response model's acquisition score)."""
    valid_ids, hyp_ids = set(shortlist["exp_id"]), {h.id for h in hypotheses} | {"explore"}
    user = "\n\n".join([
        SELECT_TASK.format(k=k),
        f"## Shortlist\n{_fmt_shortlist(shortlist)}",
        f"## Hypotheses\n{_fmt_hypotheses(hypotheses)}",
        f"## Results so far\n{_fmt_history(history, outcome)}",
    ])

    def check(out):
        picks = [p.exp_id for p in out.picks]
        problems = []
        if len(picks) != k:
            problems.append(f"choose exactly {k} experiments, not {len(picks)}")
        if len(set(picks)) != len(picks):
            problems.append("an exp_id is repeated")
        if bad := set(picks) - valid_ids:
            problems.append(f"exp_ids not in the shortlist: {sorted(bad)}")
        if bad := {p.hypothesis_id for p in out.picks} - hyp_ids:
            problems.append(f"unknown hypothesis ids: {sorted(bad)}")
        return problems

    out = llm.call("select", user, Selection, check)
    if out:
        return out.picks
    return [Pick(exp_id=e, hypothesis_id="explore", level="statistical",
                 reason="LLM output invalid twice; fell back to response-model ranking")
            for e in shortlist["exp_id"][:k]]


def predict_heldout(llm, hypotheses, heldout_info, outcome="synergy"):
    """After a run: which never-tested (held-out) lines should respond to each mechanistic hypothesis.
    heldout_info: {cell_line: genetics summary}. Only names and genetics are shown, never results.
    Returns a list of HeldoutPrediction, or None after two failed attempts."""
    mech = [h for h in hypotheses if h.level == "mechanistic" and getattr(h, "status", "open") != "dropped"]
    if not mech:
        return []
    lines, want = set(heldout_info), {h.id for h in mech}
    user = "\n\n".join([
        HELDOUT_TASK.format(outcome=_describe(outcome)),
        f"## Untested cell lines\n{_fmt_lines(heldout_info)}",
        f"## Mechanistic hypotheses\n{_fmt_hypotheses([{k: v for k, v in h.model_dump().items() if k in ('id', 'statement', 'drugs', 'rationale', 'status')} for h in mech])}",
    ])

    def check(out):
        got = [p.hypothesis_id for p in out.predictions]
        problems = []
        if sorted(got) != sorted(want):
            problems.append(f"give exactly one prediction for each of {sorted(want)}; got {got}")
        for p in out.predictions:
            if bad := set(p.predicted_responders) - lines:
                problems.append(f"{p.hypothesis_id}: not among the untested lines: {sorted(bad)}")
        return problems

    out = llm.call("predict_heldout", user, HeldoutPredictions, check)
    return out.predictions if out else None
