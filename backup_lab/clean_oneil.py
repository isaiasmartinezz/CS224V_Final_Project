"""Clean the O'Neil screen into one row per (drug pair, cell line) (backup copy of Ryan's pipeline, plan Section 5).

Input:  data/raw/drugcomb_oneil.csv (from backup_lab/fetch_oneil.py)
Output (data/processed/backup/, not committed except heldout_lines.txt):
  oneil_clean.csv   exp_id, drug_a, drug_b, cell_line, tissue, synergy, inhibition,
                    synergy_zip, synergy_loewe, synergy_bliss, synergy_hsa, n_replicates
  cell_lines.csv    cell_line, tissue, n_experiments
  heldout_lines.txt 10 held-out lines (~25%), stratified by tissue, seed 2026. Chosen once; never change.

Rules: pair order is alphabetical; replicate rows of the same (pair, line) are averaged;
rows missing a synergy score or inhibition are dropped and counted.
synergy = ZIP by default (provisional until the research team picks; see decision log);
inhibition = DrugComb css_ri, the combination sensitivity score (mean of css_row and css_col).

Usage: python -m backup_lab.clean_oneil"""
from pathlib import Path

import numpy as np
import pandas as pd

RAW = Path("data/raw/drugcomb_oneil.csv")
OUT = Path("data/processed/backup")
HELDOUT = OUT / "heldout_lines.txt"
HELDOUT_N, HELDOUT_SEED = 10, 2026
DEFAULT_SYNERGY = "zip"

# DrugComb name -> our dataset name (data/drug_names.txt). Every match checked on Nov 9 by
# looking up the DrugComb name in PubChem and comparing CIDs with data/drug_annotations.csv.
# 36/38 give the identical CID. The two platinum drugs give a different PubChem record of the
# same compound (same formula; PubChem synonyms include the common name):
#   Carboplatinum -> CID 10339178 (synonyms: Paraplatin, Carboplatinum); ours CID 426756, both C6H12N2O4Pt
#   Eloxatin (TN) -> CID 9887054 (synonyms: Xaliplatin, L-OHP); ours CID 9887053, both C8H14N2O4Pt
NAME_MAP = {
    "391210-10-9": "PD325901",            # CAS number, CID 9826528
    "5-Fluorouracil": "5-FU",
    "7-Ethyl-10-hydroxycamptothecin": "SN-38",
    "891494-63-6": "MK-8776",             # CAS number, CID 46239015
    "915019-65-7": "BEZ-235",             # CAS number, CID 11977753
    "Bortezomib": "BORTEZOMIB",
    "Carboplatinum": "CARBOPLATIN",
    "Dasatinib": "DASATINIB",
    "Deforolimus": "MK-8669",             # ridaforolimus
    "Dinaciclib": "DINACICLIB",
    "Eloxatin (TN)": "OXALIPLATIN",
    "Erlotinib": "ERLOTINIB",
    "L-778123 free base": "L778123",
    "Lapatinib": "LAPATINIB",
    "MK-1775": "AZD1775",                 # adavosertib
    "MK-2206": "MK-2206",
    "MK-4541": "MK-4541",
    "MK-5108": "MK-5108",
    "MRK003": "MRK-003",
    "Niraparib": "MK-4827",
    "Sorafenib": "SORAFENIB",
    "Sunitinib": "SUNITINIB",
    "Veliparib": "ABT-888",
    "Vorinostat": "ZOLINZA",
    "cyclophosphamide": "CYCLOPHOSPHAMIDE",
    "dexamethasone": "DEXAMETHASONE",
    "doxorubicin": "DOXORUBICIN",
    "etoposide": "ETOPOSIDE",
    "geldanamycin": "GELDANAMYCIN",
    "gemcitabine": "GEMCITABINE",
    "metformin": "METFORMIN",
    "methotrexate": "METHOTREXATE",
    "mitomycin C": "MITOMYCINE",
    "paclitaxel": "PACLITAXEL",
    "temozolomide": "TEMOZOLOMIDE",
    "topotecan": "TOPOTECAN",
    "vinblastine": "VINBLASTINE",
    "vinorelbine": "VINORELBINE",
}
SYNERGY_COLS = ["synergy_zip", "synergy_loewe", "synergy_bliss", "synergy_hsa"]


def clean(raw):
    raw = raw[raw["drug_col"].notna()].copy()  # combinations only
    unmapped = (set(raw["drug_row"]) | set(raw["drug_col"])) - set(NAME_MAP)
    if unmapped:
        raise ValueError(f"no name mapping for: {sorted(unmapped)}")
    a, b = raw["drug_row"].map(NAME_MAP), raw["drug_col"].map(NAME_MAP)
    raw["drug_a"], raw["drug_b"] = np.where(a <= b, a, b), np.where(a <= b, b, a)
    raw = raw.rename(columns={"cell_line_name": "cell_line", "tissue_name": "tissue", "css_ri": "inhibition"})

    keys = ["drug_a", "drug_b", "cell_line", "tissue"]
    out = (raw.groupby(keys)[SYNERGY_COLS + ["inhibition"]].mean()
           .join(raw.groupby(keys).size().rename("n_replicates")).reset_index())
    before = len(out)
    out = out.dropna(subset=[f"synergy_{DEFAULT_SYNERGY}", "inhibition"])
    out["synergy"] = out[f"synergy_{DEFAULT_SYNERGY}"]
    out = out.sort_values(["drug_a", "drug_b", "cell_line"]).reset_index(drop=True)
    out.insert(0, "exp_id", [f"E{i:05d}" for i in range(len(out))])
    cols = ["exp_id", "drug_a", "drug_b", "cell_line", "tissue", "synergy", "inhibition",
            *SYNERGY_COLS, "n_replicates"]
    return out[cols], before - len(out)


def choose_heldout(lines, n=HELDOUT_N, seed=HELDOUT_SEED):
    """~25% of lines, spread across tissues by largest remainder; ties and picks by a fixed seed."""
    rng = np.random.default_rng(seed)
    by_tissue = lines.groupby("tissue")["cell_line"].apply(sorted)
    share = by_tissue.apply(len) * n / len(lines)
    quota = np.floor(share).astype(int)
    leftover = n - quota.sum()
    order = sorted(share.index, key=lambda t: (-(share[t] - quota[t]), rng.random()))
    for t in order[:leftover]:
        quota[t] += 1
    picks = [l for t, members in by_tissue.items() for l in rng.permutation(members)[:quota[t]]]
    return sorted(picks)


def main():
    raw = pd.read_csv(RAW, na_values=["NULL", "NA", "\\N"], low_memory=False)
    table, dropped = clean(raw)
    OUT.mkdir(parents=True, exist_ok=True)
    table.to_csv(OUT / "oneil_clean.csv", index=False)
    lines = (table.groupby(["cell_line", "tissue"]).size().rename("n_experiments").reset_index())
    lines.to_csv(OUT / "cell_lines.csv", index=False)
    if HELDOUT.exists():
        print(f"keeping existing {HELDOUT} (chosen once, never changed)")
    else:
        HELDOUT.write_text("\n".join(choose_heldout(lines)) + "\n")

    held = set(HELDOUT.read_text().split())
    print(f"raw combination rows: {len(raw[raw['drug_col'].notna()]):,}")
    print(f"clean rows: {len(table):,} ({table[['drug_a','drug_b']].drop_duplicates().shape[0]} pairs, "
          f"{table['cell_line'].nunique()} lines, {pd.concat([table.drug_a, table.drug_b]).nunique()} drugs); "
          f"dropped for missing outcome: {dropped}")
    print(f"replicates per row: {table['n_replicates'].value_counts().sort_index().to_dict()}")
    print(f"held-out lines ({len(held)}): {sorted(held)}")
    print(lines.assign(heldout=lines.cell_line.isin(held)).groupby("tissue")["heldout"]
          .agg(["size", "sum"]).rename(columns={"size": "lines", "sum": "held_out"}).to_string())
    print(f"agent-visible experiments: {(~table.cell_line.isin(held)).sum():,}")


if __name__ == "__main__":
    main()
