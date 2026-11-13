"""Famous vs obscure drugs (plan Section 9.4): does a method only win on well-studied drugs?

Drug familiarity = number of PubMed papers naming the drug in title/abstract (dataset name or common
name, same query as retrieval). A drug is "famous" if it has at least FAMOUS_MIN papers. Counts are
continuous (2 to ~75,000; Nov 13), so 1,000 is a round cutoff, not a natural gap: 12 obscure (mostly
Merck research compounds), 26 famous; niraparib (MK-4827, 1,012) sits on the line. See decision log. Approval (WHO ATC code in
ChEMBL) is recorded too but not used: ChEMBL lacks ATC codes for some approved drugs (e.g. dasatinib).
Pair group: famous (both famous), mixed, obscure (both obscure).

  python -m backup_lab.familiarity counts   -> data/drug_familiarity.csv (committed)
  python -m backup_lab.familiarity analyze  -> strong combinations found by pair group, per method"""
import argparse
import re
import xml.etree.ElementTree as ET
from pathlib import Path

import pandas as pd

from agent.retrieval import _drug_term, _get

OUT = Path("data/drug_familiarity.csv")
FAMOUS_MIN = 1000


def pubmed_count(drug):
    xml = _get("esearch.fcgi", {"term": _drug_term(drug), "retmax": 0})
    return int(ET.fromstring(xml).findtext("Count"))


def counts():
    ann = pd.read_csv("data/drug_annotations.csv", dtype=str)
    rows = [{"drug": d, "pubmed_papers": pubmed_count(d), "approved_atc": atc != "none"}
            for d, atc in zip(ann["drug"], ann["atc_codes"])]
    df = pd.DataFrame(rows).sort_values("pubmed_papers")
    df["group"] = df["pubmed_papers"].map(lambda n: "famous" if n >= FAMOUS_MIN else "obscure")
    df.to_csv(OUT, index=False)
    print(df.to_string(index=False))


def pair_group(a, b, fam):
    k = (fam.get(a) == "famous") + (fam.get(b) == "famous")
    return {2: "famous", 1: "mixed", 0: "obscure"}[k]


def analyze(definition="joint_within_line"):
    from agent.lab_source import get_source, make_lab, results_dir, truth_for
    from backup_lab.thresholds import strong_labels
    source = get_source()
    out_dir = results_dir(source)
    fam = dict(pd.read_csv(OUT)[["drug", "group"]].values)
    truth = truth_for(make_lab(source))
    labels, _ = strong_labels(truth, definition)
    groups = pd.Series([pair_group(a, b, fam) for a, b in zip(truth["drug_a"], truth["drug_b"])], index=truth.index)
    pool = pd.DataFrame({"share_of_pool": groups.value_counts(normalize=True),
                         "share_of_strong": groups[labels].value_counts(normalize=True)})
    rows = []
    pat = re.compile(r"run_log_(?P<m>.+)_(?P<t>synergy|inhibition|joint)_seed\d+\.csv")
    for path in sorted(out_dir.glob("run_log_*.csv")):
        m = pat.fullmatch(path.name)
        if not m:
            continue
        log = pd.read_csv(path)
        g = log["exp_id"].map(groups)
        s = log["exp_id"].map(labels).fillna(False).astype(bool)
        for grp in ("famous", "mixed", "obscure"):
            rows.append({"method": f"{m['m']}:{m['t']}", "group": grp, "picked": int((g == grp).sum()),
                         "strong_found": int((s & (g == grp)).sum())})
    res = pd.DataFrame(rows).groupby(["method", "group"]).mean().unstack("group").round(1)
    print(f"pool (definition={definition}):\n{pool.round(3).to_string()}\n\nmean per run:\n{res.to_string()}")
    res.to_csv(out_dir / "famous_vs_obscure.csv")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("what", choices=["counts", "analyze"])
    args = ap.parse_args()
    counts() if args.what == "counts" else analyze()


if __name__ == "__main__":
    main()
