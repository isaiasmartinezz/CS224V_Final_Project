"""The on/off switch for the backup copy of Ryan's work.

LAB_SOURCE picks whose lab, data, and response model every runner uses:
  backup  Isaias's copy of Ryan's tasks in backup_lab/ (data in data/processed/backup/)   [default]
  ryan    Ryan's own lab/ package and data/processed/ files
  stub    the fake lab in agent/stub_lab.py (random scores, for quick checks)
Set it in .env (LAB_SOURCE=ryan) or per run with --lab ryan. Turning the backup off = LAB_SOURCE=ryan.
Results go to results/<source>/ so the two versions never mix."""
import os
from pathlib import Path

from dotenv import load_dotenv

SOURCES = ("backup", "ryan", "stub")
DEFAULT = "backup"
RYAN_DATA = Path("data/processed/oneil_clean.csv")
RYAN_HELDOUT = Path("data/processed/heldout_lines.txt")
BACKUP_LINES = Path("data/processed/backup/cell_lines.csv")


def get_source(cli_value=None):
    load_dotenv()
    source = (cli_value or os.getenv("LAB_SOURCE") or DEFAULT).strip().lower()
    if source not in SOURCES:
        raise SystemExit(f"LAB_SOURCE must be one of {SOURCES}, got {source!r}")
    return source


def results_dir(source):
    """results/<source>/, or results/<source>_<metric>/ when SYNERGY_METRIC overrides the default
    (e.g. the Bliss robustness check), so runs with different synergy scores never mix."""
    load_dotenv()
    metric = (os.getenv("SYNERGY_METRIC") or "").strip().lower()
    d = Path("results") / (f"{source}_{metric}" if metric and source == "backup" else source)
    d.mkdir(parents=True, exist_ok=True)
    return d


def make_lab(source, budget=250):
    if source == "stub":
        from agent.stub_lab import StubLab
        return StubLab(budget=budget, seed=0)  # same fake world every seed
    if source == "backup":
        from backup_lab.sim_lab import SimLab
        load_dotenv()
        return SimLab(budget=budget, synergy_metric=os.getenv("SYNERGY_METRIC") or None)
    try:
        from lab.sim_lab import SimLab
    except ImportError:
        raise SystemExit("LAB_SOURCE=ryan but lab/sim_lab.py isn't in the repo yet. "
                         "Use LAB_SOURCE=backup (or pull Ryan's latest code).")
    return SimLab(RYAN_DATA, RYAN_HELDOUT, budget=budget)


def cell_line_tissue(source):
    """{cell_line: tissue}, public metadata only (no results). Empty if unavailable."""
    import pandas as pd
    path = BACKUP_LINES if source == "backup" else RYAN_DATA if source == "ryan" else None
    if path is None or not path.exists():
        return {}
    df = pd.read_csv(path)
    return dict(zip(df["cell_line"], df["tissue"])) if "tissue" in df else {}


def line_features_for(source):
    """Cell-line genetics for the model, or None if not built (run backup_lab.cell_line_features)."""
    import pandas as pd
    d = Path("data/processed/backup")
    if source != "backup" or not (d / "cell_line_features.csv").exists():
        return None
    return {"line": pd.read_csv(d / "cell_line_features.csv", index_col="cell_line"),
            "target_expr": pd.read_csv(d / "target_expression.csv", index_col="cell_line")}


def line_summaries_for(source):
    """{cell_line: plain-text genetics} for the LLM, or {} if not built."""
    import pandas as pd
    path = Path("data/processed/backup/cell_line_summaries.csv")
    if source != "backup" or not path.exists():
        return {}
    df = pd.read_csv(path)
    return dict(zip(df["cell_line"], df["summary"]))


def make_response_model(source, cell_lines, seed=0):
    """A model with fit(history, outcome) and predict(candidates) -> (mean, std), or None
    (then the agent shortlists at random). The stub lab gets None to stay fast."""
    if source == "stub":
        return None
    if source == "ryan":
        try:
            from lab.response_model import ResponseModel
        except ImportError:
            print("note: lab/response_model.py not found; agent will shortlist at random")
            return None
        return ResponseModel(cell_lines, seed=seed)  # assumes the interface in notes/interface.md
    from backup_lab.response_model import ResponseModel
    return ResponseModel(cell_lines, tissue=cell_line_tissue(source), seed=seed,
                         line_features=line_features_for(source))


def truth_for(lab):
    """All non-held-out results, for the strong thresholds. Evaluation only."""
    return lab._all_results()
