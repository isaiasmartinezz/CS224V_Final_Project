"""Turn data/drug_annotations_draft.csv into data/drug_annotations.csv.
Adds hand-written fields with their sources, so every manual choice is visible here.

drug_class restates, in plain words, a sourced field: the WHO ATC group (fetched from
ChEMBL's atc_class endpoint), the ChEMBL mechanism, or the cited paper for literature rows.
Blank fields become "unknown"; a missing ATC code becomes "none" (not WHO-classified)."""
import pandas as pd

DRAFT = "data/drug_annotations_draft.csv"
OUT = "data/drug_annotations.csv"

# drug -> (drug_class, source of the class)
DRUG_CLASS = {
    "5-FU": ("pyrimidine analogue; thymidylate synthase inhibitor", "ATC L01BC + ChEMBL"),
    "ABT-888": ("PARP inhibitor", "ATC L01XK + ChEMBL"),
    "AZD1775": ("WEE1 kinase inhibitor", "ChEMBL"),
    "BEZ-235": ("dual PI3K / mTOR inhibitor", "ChEMBL"),
    "BORTEZOMIB": ("proteasome inhibitor", "ATC L01XG + ChEMBL"),
    "CARBOPLATIN": ("platinum compound; acts on DNA", "ATC L01XA + ChEMBL"),
    "CYCLOPHOSPHAMIDE": ("nitrogen mustard alkylating agent; acts on DNA", "ATC L01AA + ChEMBL"),
    "DASATINIB": ("multi-kinase inhibitor (BCR-ABL, SRC, KIT, PDGFR-beta, EPHA2)", "ChEMBL"),
    "DEXAMETHASONE": ("glucocorticoid (glucocorticoid receptor agonist)", "ATC H02AB + ChEMBL"),
    "DINACICLIB": ("CDK inhibitor (CDK1, 2, 5, 9)", "ChEMBL"),
    "DOXORUBICIN": ("anthracycline; topoisomerase II inhibitor", "ATC L01DB + ChEMBL"),
    "ERLOTINIB": ("EGFR tyrosine kinase inhibitor", "ATC L01EB + ChEMBL"),
    "ETOPOSIDE": ("podophyllotoxin derivative; topoisomerase II inhibitor", "ATC L01CB + ChEMBL"),
    "GELDANAMYCIN": ("HSP90 inhibitor", "PMID 9108479"),
    "GEMCITABINE": ("pyrimidine analogue; ribonucleotide reductase inhibitor", "ATC L01BC + ChEMBL"),
    "L778123": ("farnesyltransferase and geranylgeranyltransferase-I inhibitor", "PMID 15248757"),
    "LAPATINIB": ("HER2 and EGFR tyrosine kinase inhibitor", "ATC L01EH + ChEMBL"),
    "METFORMIN": ("biguanide; mitochondrial complex I inhibitor", "ATC A10BA + ChEMBL"),
    "METHOTREXATE": ("folic acid analogue; DHFR inhibitor", "ATC L01BA + ChEMBL"),
    "MITOMYCINE": ("cytotoxic antibiotic; acts on DNA", "ATC L01DC + ChEMBL"),
    "MK-2206": ("AKT inhibitor", "ChEMBL"),
    "MK-4541": ("selective androgen receptor modulator (SARM)", "PMID 24565564"),
    "MK-4827": ("PARP inhibitor", "ATC L01XK + ChEMBL"),
    "MK-5108": ("Aurora A kinase inhibitor", "ChEMBL"),
    "MK-8669": ("mTOR inhibitor", "ATC L01EG + ChEMBL"),
    "MK-8776": ("CHK1 inhibitor", "ChEMBL"),
    "MRK-003": ("gamma-secretase inhibitor (blocks Notch signaling)", "PMID 17804716"),
    "OXALIPLATIN": ("platinum compound; acts on DNA", "ATC L01XA + ChEMBL"),
    "PACLITAXEL": ("taxane; tubulin inhibitor", "ATC L01CD + ChEMBL"),
    "PD325901": ("MEK1/2 inhibitor", "ATC L01EE + ChEMBL"),
    "SN-38": ("topoisomerase I inhibitor", "ChEMBL"),
    "SORAFENIB": ("multi-kinase inhibitor (RAF, VEGFR, PDGFR-beta, KIT, FLT3, RET)", "ATC L01EX + ChEMBL"),
    "SUNITINIB": ("multi-kinase inhibitor (VEGFR, PDGFR, KIT, FLT3, RET, CSF1R)", "ATC L01EX + ChEMBL"),
    "TEMOZOLOMIDE": ("alkylating agent; acts on DNA", "ATC L01AX + ChEMBL"),
    "TOPOTECAN": ("topoisomerase I inhibitor", "ATC L01CE + ChEMBL"),
    "VINBLASTINE": ("vinca alkaloid; tubulin inhibitor", "ATC L01CA + ChEMBL"),
    "VINORELBINE": ("vinca alkaloid; tubulin inhibitor", "ATC L01CA + ChEMBL"),
    "ZOLINZA": ("HDAC inhibitor", "ATC L01XH + ChEMBL"),
}

# Drugs with no ChEMBL mechanism: values taken from the cited abstracts (PubMed)
LITERATURE = {
    "GELDANAMYCIN": {
        "targets": "Heat shock protein HSP 90",
        "mechanism": "Binds the N-terminal ATP-binding pocket of Hsp90 and blocks its chaperone function",
        "action_type": "INHIBITOR",
        "sources": "PMID 9108479; PMID 9295332",
    },
    "L778123": {
        "targets": "Protein farnesyltransferase; Protein geranylgeranyltransferase type I",
        "mechanism": "Dual inhibitor of farnesyltransferase and geranylgeranyltransferase-I (blocks Ras prenylation)",
        "action_type": "INHIBITOR",
        "sources": "PMID 15248757; PMID 12479371",
    },
    "MK-4541": {
        "targets": "Androgen receptor",
        "mechanism": "Selective androgen receptor modulator; anti-androgenic in prostate cancer models, anabolic in muscle",
        "action_type": "MODULATOR",
        "sources": "PMID 24565564; PMID 27106747",
    },
    "MRK-003": {
        "targets": "Gamma-secretase",
        "mechanism": "Gamma-secretase inhibitor; blocks Notch receptor activation",
        "action_type": "INHIBITOR",
        "sources": "PMID 17804716; PMID 22752426",
    },
}


def main():
    d = pd.read_csv(DRAFT, dtype=str).fillna("")
    assert set(d["drug"]) == set(DRUG_CLASS), "every drug needs a drug_class"

    for i, row in d.iterrows():
        drug = row["drug"]
        notes = [row["notes"]] if row["notes"] else []
        if drug in LITERATURE:
            lit = LITERATURE[drug]
            for col in ["targets", "mechanism", "action_type"]:
                d.at[i, col] = lit[col]
            notes.append(f"targets/mechanism from literature: {lit['sources']}")
        cls, source = DRUG_CLASS[drug]
        d.at[i, "drug_class"] = cls
        notes.append(f"drug_class source: {source}")
        d.at[i, "notes"] = "; ".join(notes)
        d.at[i, "status"] = "needs sign-off"  # Isaias flips to "done" after reading the row

    d["atc_codes"] = d["atc_codes"].replace("", "none")
    d = d.replace("", "unknown")
    d.to_csv(OUT, index=False)
    print(f"Saved {len(d)} rows to {OUT}")
    print("unknown cells per column:", (d == "unknown").sum()[lambda s: s > 0].to_dict())


if __name__ == "__main__":
    main()
