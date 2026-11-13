"""Estimate the cost of one real agent run without an API key.

Runs the full agent (one seed, joint target) on the real lab with real PubMed retrieval, but with a
fake Claude that returns valid answers, and measures every prompt it would send.
  input tokens  ~ characters / 4 (a rough rule for English + tables; the real count can differ ~20%)
  output tokens are a guess: adaptive thinking at effort "high" also bills thinking as output, so we
                give a range per call (OUTPUT_LOW to OUTPUT_HIGH)
Prices: agent.prompts.PRICE (Opus 5.5). Replace this estimate with the real number from
results/llm_logs after the first real run.

Usage: python experiments/estimate_cost.py"""
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent import prompts  # noqa: E402
from agent.agent import LLMChooser, run_agent  # noqa: E402
from agent.lab_source import cell_line_tissue, line_summaries_for, make_lab, make_response_model  # noqa: E402
from agent.prompts import LLM, SYSTEM, predict_heldout  # noqa: E402
from tests.test_agent_llm import FakeClaude  # noqa: E402

CHARS_PER_TOKEN = 4
OUTPUT_LOW, OUTPUT_HIGH = 1_500, 6_000


class Recorder(FakeClaude):
    def __init__(self):
        super().__init__()
        self.sizes = defaultdict(list)

    def create(self, **kw):
        step = kw["output_config"]["format"]["schema"]["title"]
        self.sizes[step].append(len(kw["system"]) + len(kw["messages"][0]["content"]))
        return super().create(**kw)


def main():
    prompts.LOG_DIR = Path("/tmp") / "cost_estimate_logs"  # don't mix fake calls into real logs
    lab = make_lab("backup")
    lines = lab.candidates()["cell_line"].unique()
    fake = Recorder()
    summaries = line_summaries_for("backup")
    chooser = LLMChooser("cost_estimate", outcome="joint", llm=LLM("cost_estimate", client=fake),
                         model=make_response_model("backup", lines, seed=0),
                         tissue=cell_line_tissue("backup"), line_info=summaries)
    run_agent(lab, seed=0, chooser=chooser)
    predict_heldout(chooser.llm, list(chooser.book.items.values()),
                    {l: summaries.get(l, "unknown") for l in lab._heldout}, "joint")

    n_calls = sum(len(v) for v in fake.sizes.values())
    in_tok = sum(sum(v) for v in fake.sizes.values()) / CHARS_PER_TOKEN
    price = prompts.PRICE
    low = in_tok * price["input"] + n_calls * OUTPUT_LOW * price["output"]
    high = in_tok * price["input"] + n_calls * OUTPUT_HIGH * price["output"]
    for step, v in fake.sizes.items():
        print(f"{step:20} {len(v):3} calls, prompt ~{sum(v) / len(v) / CHARS_PER_TOKEN:,.0f} tokens on average "
              f"(max ~{max(v) / CHARS_PER_TOKEN:,.0f})")
    print(f"\none run: {n_calls} calls, ~{in_tok:,.0f} input tokens; output {OUTPUT_LOW:,}-{OUTPUT_HIGH:,} per call")
    print(f"estimated cost per run: ${low:.2f} - ${high:.2f}  (no retries; a retry repeats a call)")
    for label, runs in [("main comparison: 5 seeds", 5), ("+ 3 ablations x 5 seeds", 20)]:
        print(f"  {label:28} ${low * runs:,.0f} - ${high * runs:,.0f}")


if __name__ == "__main__":
    main()
