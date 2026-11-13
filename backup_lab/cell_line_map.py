"""O'Neil / DrugComb cell-line name -> Cell Model Passports model_id. Checked Nov 13 against
model_list_latest.csv.gz: name (ignoring case and punctuation), tissue, and cancer type all agree.
None = no confident match: genetics are marked unknown for that line (never guessed)."""

CMP_ID = {
    "A2058": "SIDM00797", "A2780": "SIDM00210", "A375": "SIDM00795", "A427": "SIDM00810",
    "CAOV3": "SIDM00919", "DLD1": "SIDM00787", "EFM192B": "SIDM01054", "ES2": "SIDM00861",
    "HCT116": "SIDM00783", "HT144": "SIDM00695", "HT29": "SIDM00136", "KPL1": "SIDM00147",
    "LOVO": "SIDM00839", "MDAMB436": "SIDM00629", "NCI-H460": "SIDM00144", "NCIH1650": "SIDM00745",
    "NCIH2122": "SIDM00702", "NCIH23": "SIDM00138", "NCIH520": "SIDM01130", "OCUBM": "SIDM00241",
    "OV90": "SIDM01141", "OVCAR3": "SIDM00105", "PA1": "SIDM01140", "RKO": "SIDM01090",
    "RPMI7951": "SIDM01087", "SK-OV-3": "SIDM00079", "SKMEL30": "SIDM00392", "SKMES1": "SIDM01103",
    "SW-620": "SIDM00841", "SW837": "SIDM00833", "T-47D": "SIDM00097", "UACC62": "SIDM00107",
    "UWB1289": "SIDM00815", "VCAP": "SIDM01077", "ZR751": "SIDM00314",
    # Matched by standard full name (CMP has no exact short-name match):
    "MSTO": "SIDM00640",          # MSTO-211H; CMP tissue Lung, cancer type Mesothelioma
    "LNCAP": "SIDM00683",         # LNCaP-Clone-FGC (synonyms LNCaP.FGC; LNCaP-ATCC)
    # Derived line: UWB1.289 with BRCA1 restored. Uses the parent's profile, but BRCA1 is set to unknown.
    "UWB1289+BRCA1": "SIDM00815",
    # Not confidently in CMP (only COLO-320 and COLO-320-HSR exist; not confirmed to be COLO 320DM):
    "COLO320DM": None,
}
UNKNOWN_GENES = {"UWB1289+BRCA1": {"BRCA1"}}
