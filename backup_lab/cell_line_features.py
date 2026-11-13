"""Cell-line genetics for the response model and the agent (Cell Model Passports, see fetch_cell_lines.py).

Outputs in data/processed/backup/:
  cell_line_features.csv    one row per O'Neil line: has_genetics, msi_status, mut_<GENE> (1/0/NaN=unknown)
                            for genes with a driver mutation in >= 3 of our lines or that a drug targets,
                            amp_<GENE> / del_<GENE> for drug-target genes
  target_expression.csv     cell_line x drug: mean expression of the drug's ChEMBL target genes. CMP's
                            rsem_tpm column is already log2-scaled (checked Nov 13: max 16.6; ACTB/GAPDH ~11),
                            so it is used as-is
                            (NaN when the drug has no target genes or the line has no expression data)
  cell_line_summaries.csv   cell_line, summary: short plain text for the LLM, e.g.
                            "colorectal; MSI-H; driver mutations: BRAF V600E, PIK3CA H1047R; amplified: none"
Unknowns stay unknown (NaN / "unknown"), e.g. COLO320DM (no confident CMP match) and BRCA1 in UWB1289+BRCA1.

Usage: python -m backup_lab.cell_line_features"""
from pathlib import Path

import numpy as np
import pandas as pd

from backup_lab.cell_line_map import CMP_ID, UNKNOWN_GENES

RAW = Path("data/raw/cmp")
OUT = Path("data/processed/backup")
MIN_LINES = 3


def target_genes():
    t = pd.read_csv("data/drug_target_genes.csv", dtype=str)
    return {d: [] if g == "unknown" else g.split("; ") for d, g in zip(t["drug"], t["genes"])}


def load():
    models = pd.read_csv(RAW / "model_list_latest.csv.gz", low_memory=False).set_index("model_id")
    mut = pd.read_csv(RAW / "mutations_summary_latest.csv.gz", low_memory=False)
    mut = mut[(mut["cancer_driver"] == "t") & (mut["duplicate"] == "f")]
    cnv = pd.read_csv(RAW / "cnv_summary_latest.csv.gz", low_memory=False)
    rna = pd.read_csv(RAW / "rnaseq_oneil_lines.csv", low_memory=False)
    rna = rna[rna["duplicate"] == "f"]
    return models, mut, cnv, rna


def build(lines):
    models, mut, cnv, rna = load()
    targets = target_genes()
    all_targets = sorted({g for gs in targets.values() for g in gs})
    ids = {l: CMP_ID.get(l) for l in lines}
    ours = {i for i in ids.values() if i}
    mut = mut[mut["model_id"].isin(ours)]
    counts = mut.groupby("gene_symbol")["model_id"].nunique()
    panel = sorted(set(counts[counts >= MIN_LINES].index) | (set(mut["gene_symbol"]) & set(all_targets)))

    rows, summaries = [], []
    expr = (rna[rna["model_id"].isin(ours)].assign(v=lambda d: d["rsem_tpm"].astype(float))
            .groupby(["model_id", "gene_symbol"])["v"].mean().unstack())
    for line, mid in ids.items():
        row = {"cell_line": line, "cmp_id": mid or "unknown"}
        sequenced = bool(mid) and str(models.loc[mid, "mutation_data"]) == "True"
        row["has_genetics"] = int(sequenced)
        row["msi_status"] = models.loc[mid, "msi_status"] if mid and pd.notna(models.loc[mid, "msi_status"]) else "unknown"
        m = mut[mut["model_id"] == mid] if mid else mut.iloc[0:0]
        for g in panel:
            row[f"mut_{g}"] = (int(g in set(m["gene_symbol"])) if sequenced else np.nan)
        # a gene can appear once per data source; amplified/deleted if any source says so
        c = (cnv[cnv["model_id"] == mid].groupby("symbol")["cn_category"].agg(set).to_dict() if mid else {})
        for g in all_targets:
            row[f"amp_{g}"] = int("Amplification" in c.get(g, set())) if c else np.nan
            row[f"del_{g}"] = int("Deletion" in c.get(g, set())) if c else np.nan
        for g in UNKNOWN_GENES.get(line, ()):
            for k in (f"mut_{g}", f"amp_{g}", f"del_{g}"):
                if k in row:
                    row[k] = np.nan
        rows.append(row)

        if not mid:
            summaries.append({"cell_line": line, "summary": "genetics unknown (no confident Cell Model Passports match)"})
            continue
        hits = m.drop_duplicates(["gene_symbol", "protein_mutation"])
        hits = hits[~hits["gene_symbol"].isin(UNKNOWN_GENES.get(line, ()))]
        change = lambda p: "(protein change not given)" if p in ("p.?", "-", "") or pd.isna(p) else p.removeprefix("p.")
        muts = ", ".join(f"{g} {change(p)}" for g, p in zip(hits["gene_symbol"], hits["protein_mutation"])
                         if g in panel) or ("none in panel" if sequenced else "unknown")
        amps = sorted(g for g in all_targets if "Amplification" in c.get(g, set()))
        text = (f"{models.loc[mid, 'cancer_type']}; MSI: {row['msi_status']}; driver mutations: {muts}; "
                f"amplified drug targets: {(', '.join(amps) or 'none') if c else 'unknown'}")
        for g in UNKNOWN_GENES.get(line, ()):
            text += f"; {g}: unknown (engineered derivative)"
        summaries.append({"cell_line": line, "summary": text})

    feats = pd.DataFrame(rows).set_index("cell_line")
    texpr = pd.DataFrame({d: [expr.loc[ids[l], [g for g in gs if g in expr.columns]].mean()
                              if ids[l] in expr.index and any(g in expr.columns for g in gs) else np.nan
                              for l in lines] for d, gs in targets.items()}, index=lines)
    texpr.index.name = "cell_line"
    return feats, texpr, pd.DataFrame(summaries)


def main():
    lines = pd.read_csv(OUT / "cell_lines.csv")["cell_line"].tolist()
    feats, texpr, summ = build(lines)
    feats.to_csv(OUT / "cell_line_features.csv")
    texpr.round(3).to_csv(OUT / "target_expression.csv")
    summ.to_csv(OUT / "cell_line_summaries.csv", index=False)
    mut_cols = [c for c in feats if c.startswith("mut_")]
    print(f"{len(feats)} lines; with genetics: {feats['has_genetics'].sum()}; mutation panel: {len(mut_cols)} genes; "
          f"target-expression: {texpr.notna().all(axis=1).sum()} lines complete, drugs with targets: "
          f"{texpr.notna().any().sum()}")
    print(summ.head(6).to_string(index=False))


if __name__ == "__main__":
    main()
