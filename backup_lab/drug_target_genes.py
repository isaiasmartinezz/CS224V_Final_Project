"""Gene symbols of each drug's targets, from ChEMBL (mechanism -> target -> target components).
Used to pick which genes' expression to show the model and the agent.
Drugs without a ChEMBL mechanism (or non-protein targets like DNA) get "unknown"; nothing is guessed.
Output: data/drug_target_genes.csv (drug, chembl_id, target_chembl_ids, genes, source). Committed.

Usage: python -m backup_lab.drug_target_genes"""
import time
from pathlib import Path

import pandas as pd
import requests

API = "https://www.ebi.ac.uk/chembl/api/data"
OUT = Path("data/drug_target_genes.csv")


def get(path, **params):
    for attempt in range(3):
        r = requests.get(f"{API}/{path}", params={"format": "json", **params}, timeout=60)
        if r.ok:
            time.sleep(0.2)
            return r.json()
        time.sleep(2 * (attempt + 1))
    r.raise_for_status()


def target_genes(target_id):
    t = get(f"target/{target_id}")
    genes = set()
    for comp in t.get("target_components", []):
        for syn in comp.get("target_component_synonyms", []):
            if syn.get("syn_type") == "GENE_SYMBOL":
                genes.add(syn["component_synonym"].upper())
                break  # first gene symbol per component is the primary one
    return genes


def main():
    ann = pd.read_csv("data/drug_annotations.csv", dtype=str)
    rows = []
    for drug, chembl in zip(ann["drug"], ann["chembl_id"]):
        if not isinstance(chembl, str) or chembl == "unknown":
            rows.append({"drug": drug, "chembl_id": "unknown", "target_chembl_ids": "", "genes": "unknown",
                         "source": "no ChEMBL ID"})
            continue
        mechs = get("mechanism", parent_molecule_chembl_id=chembl, limit=100)["mechanisms"]
        tids = sorted({m["target_chembl_id"] for m in mechs if m.get("target_chembl_id")})
        genes = set().union(*[target_genes(t) for t in tids]) if tids else set()
        rows.append({"drug": drug, "chembl_id": chembl, "target_chembl_ids": "; ".join(tids),
                     "genes": "; ".join(sorted(genes)) or "unknown",
                     "source": "ChEMBL mechanism + target components" if genes
                     else "no protein target gene in ChEMBL (e.g. DNA) or no mechanism"})
        print(f"{drug:18} {rows[-1]['genes']}")
    pd.DataFrame(rows).to_csv(OUT, index=False)
    print(f"-> {OUT}")


if __name__ == "__main__":
    main()
