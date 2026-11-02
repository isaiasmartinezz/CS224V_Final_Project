"""Draft drug annotations from PubChem (structure) and ChEMBL (target, mechanism).
Everything here is a first draft: review every row by hand before using it."""
import csv
import time
from pathlib import Path
from urllib.parse import quote

import requests

NAMES_FILE = Path("data/drug_names.txt")
OUT_FILE = Path("data/drug_annotations_draft.csv")
PUBCHEM = "https://pubchem.ncbi.nlm.nih.gov/rest/pug"
CHEMBL = "https://www.ebi.ac.uk/chembl/api/data"

# Dataset spelling -> name the databases recognize
SEARCH_NAMES = {
    "5-FU": "fluorouracil",
    "ABT-888": "veliparib",
    "AZD1775": "adavosertib",
    "BEZ-235": "dactolisib",
    "L778123": "L-778123",
    "MITOMYCINE": "mitomycin",
    "MK-4827": "niraparib",
    "MK-8669": "ridaforolimus",
    "MK-8776": "SCH 900776",
    "PD325901": "PD0325901",
    "ZOLINZA": "vorinostat",
}

COLUMNS = [
    "drug", "search_name", "pubchem_cid", "smiles",
    "chembl_id", "chembl_name", "targets", "mechanism", "action_type",
    "atc_codes", "drug_class", "status", "notes",
]


def get_json(url, params=None):
    try:
        r = requests.get(url, params=params, timeout=30)
        if r.ok:
            return r.json()
    except (requests.RequestException, ValueError):
        pass
    return None


def pubchem(name):
    for prop in ("SMILES", "CanonicalSMILES"):
        data = get_json(f"{PUBCHEM}/compound/name/{quote(name)}/property/{prop}/JSON")
        if data:
            row = data["PropertyTable"]["Properties"][0]
            smiles = next((v for k, v in row.items() if "SMILES" in k), "")
            return row.get("CID", ""), smiles
    return "", ""


def pubchem_chembl_xref(cid):
    """ChEMBL ID that PubChem lists among the compound's synonyms, if any."""
    data = get_json(f"{PUBCHEM}/compound/cid/{cid}/synonyms/JSON") if cid else None
    if not data:
        return ""
    synonyms = data["InformationList"]["Information"][0].get("Synonym", [])
    return next((s for s in synonyms if s.startswith("CHEMBL") and s[6:].isdigit()), "")


def find_molecule(name, cid):
    """Exact preferred name, then exact synonym, then PubChem's cross-reference.
    No free-text search: it matched the wrong molecule for MRK-003."""
    for params in ({"pref_name__iexact": name},
                   {"molecule_synonyms__molecule_synonym__iexact": name}):
        data = get_json(f"{CHEMBL}/molecule.json", {**params, "limit": 5})
        if data and data.get("molecules"):
            return data["molecules"][0], "name"
    xref = pubchem_chembl_xref(cid)
    if xref:
        mol = get_json(f"{CHEMBL}/molecule/{xref}.json")
        if mol:
            return mol, "pubchem_xref"
    return None, ""


def chembl(name, cid):
    mol, match = find_molecule(name, cid)
    if not mol:
        return {}
    chembl_id = mol["molecule_chembl_id"]
    parent = (mol.get("molecule_hierarchy") or {}).get("parent_chembl_id") or chembl_id

    # Mechanisms are often filed under a salt form, so filter by parent to catch all forms
    mech = get_json(f"{CHEMBL}/mechanism.json", {"parent_molecule_chembl_id": parent}) or {}
    mechanisms, actions, targets = [], [], []
    for m in mech.get("mechanisms", []):
        mechanisms.append(m.get("mechanism_of_action") or "")
        actions.append(m.get("action_type") or "")
        tid = m.get("target_chembl_id")
        if tid:
            t = get_json(f"{CHEMBL}/target/{tid}.json") or {}
            targets.append(t.get("pref_name") or tid)

    join = lambda xs: "; ".join(dict.fromkeys(x for x in xs if x))
    return {
        "chembl_id": parent,
        "chembl_name": mol.get("pref_name") or "",
        "match": match,
        "targets": join(targets),
        "mechanism": join(mechanisms),
        "action_type": join(actions),
        "atc_codes": "; ".join(mol.get("atc_classifications") or []),
    }


def main():
    names = [line.strip() for line in NAMES_FILE.read_text().splitlines() if line.strip()]
    with OUT_FILE.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        writer.writeheader()
        for drug in names:
            query = SEARCH_NAMES.get(drug.upper(), drug)
            cid, smiles = pubchem(query)
            info = chembl(query, cid)
            complete = bool(smiles) and bool(info.get("mechanism"))
            if not info:
                notes = "not found in ChEMBL"
            elif info["match"] == "pubchem_xref":
                notes = f"ChEMBL ID via PubChem CID {cid} cross-reference"
            else:
                notes = ""
            if info and not info.get("mechanism"):
                notes = "; ".join(filter(None, [notes, "no mechanism record in ChEMBL"]))
            writer.writerow({
                "drug": drug,
                "search_name": query,
                "pubchem_cid": cid,
                "smiles": smiles,
                **{k: info.get(k, "") for k in
                   ["chembl_id", "chembl_name", "targets", "mechanism", "action_type", "atc_codes"]},
                "drug_class": "",
                "status": "check" if complete else "NEEDS WORK",
                "notes": notes,
            })
            print(f"{drug:14s} structure: {'yes' if smiles else 'NO ':4s} "
                  f"mechanism: {'yes' if info.get('mechanism') else 'NO'}")
            time.sleep(0.3)
    print(f"\nSaved draft to {OUT_FILE}")


if __name__ == "__main__":
    main()
