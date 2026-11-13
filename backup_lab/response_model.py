"""Response model with uncertainty (plan Section 8.1).

Predicts an outcome (synergy or inhibition) for any untested experiment.
- Features per experiment (order of the two drugs does not matter, so drug features are summed):
  Morgan fingerprints of both drugs (RDKit, radius 2, 256 bits, from data/drug_annotations.csv SMILES),
  their ChEMBL targets (multi-hot), drug identity (multi-hot), cell line (one-hot), tissue (one-hot, if given),
  and, when line_features is given (Cell Model Passports, see cell_line_features.py): the line's driver
  mutations and target-gene amplifications/deletions, plus the line's expression of each drug's target
  genes (min and max over the two drugs, so drug order doesn't matter). Unknown values are filled with
  the column mean (expression) or 0 (mutation/copy number) and flagged with a has_genetics column.
- Model: random forest. Uncertainty = spread (std) of the individual trees' predictions.
- Retrained from scratch on all results seen so far every time fit() is called.
"""
import numpy as np
import pandas as pd
from rdkit import Chem, RDLogger
from rdkit.Chem import rdFingerprintGenerator
from sklearn.ensemble import RandomForestRegressor

RDLogger.DisableLog("rdApp.*")
ANNOTATIONS = "data/drug_annotations.csv"
FP_BITS = 256


def drug_features(annotations_path=ANNOTATIONS):
    """One row per drug: fingerprint bits + target multi-hot + identity one-hot."""
    ann = pd.read_csv(annotations_path, dtype=str).set_index("drug")
    gen = rdFingerprintGenerator.GetMorganGenerator(radius=2, fpSize=FP_BITS)
    fps = []
    for drug, smi in ann["smiles"].items():
        mol = Chem.MolFromSmiles(smi) if isinstance(smi, str) and smi != "unknown" else None
        fps.append(gen.GetFingerprintAsNumPy(mol).astype(float) if mol else np.zeros(FP_BITS))
    fp = pd.DataFrame(fps, index=ann.index).add_prefix("fp_")
    targets = (ann["targets"].fillna("unknown").str.get_dummies(sep="; ")
               .drop(columns=["unknown"], errors="ignore").add_prefix("target_"))
    ident = pd.get_dummies(ann.index.to_series(), dtype=float).add_prefix("drug_")
    return pd.concat([fp, targets, ident], axis=1).astype(float)


class ResponseModel:
    def __init__(self, cell_lines, tissue=None, n_trees=100, seed=0, annotations_path=ANNOTATIONS,
                 line_features=None):
        """cell_lines: all line names the model may see (from lab.candidates()).
        tissue: optional {cell_line: tissue} (public metadata, not results)."""
        self.drugs = drug_features(annotations_path)
        lines = sorted(set(cell_lines))
        line_df = pd.get_dummies(pd.Series(lines, index=lines), dtype=float).add_prefix("line_")
        if tissue:
            t = pd.get_dummies(pd.Series({l: tissue.get(l, "unknown") for l in lines}), dtype=float)
            line_df = line_df.join(t.add_prefix("tissue_"))
        self.texpr = None
        if line_features is not None:
            gen = line_features["line"].reindex(lines)
            num = gen.select_dtypes("number").fillna(0.0).add_prefix("gen_")
            line_df = line_df.join(num)
            te = line_features["target_expr"].reindex(lines)
            self.texpr = te.fillna(te.mean()).fillna(0.0)
        self.lines = line_df
        self.n_trees, self.seed = n_trees, seed
        self.forest = None

    def featurize(self, table):
        a = self.drugs.loc[table["drug_a"]].to_numpy()
        b = self.drugs.loc[table["drug_b"]].to_numpy()
        c = self.lines.loc[table["cell_line"]].to_numpy()
        parts = [a + b, c]
        if self.texpr is not None:
            te = self.texpr.to_numpy()
            row = self.texpr.index.get_indexer(table["cell_line"])
            col_a = self.texpr.columns.get_indexer(table["drug_a"])
            col_b = self.texpr.columns.get_indexer(table["drug_b"])
            xa = np.where(col_a >= 0, te[row, col_a], 0.0)
            xb = np.where(col_b >= 0, te[row, col_b], 0.0)
            parts.append(np.column_stack([np.minimum(xa, xb), np.maximum(xa, xb)]))
        return np.hstack(parts)

    def fit(self, history, outcome):
        y = pd.to_numeric(history[outcome]).to_numpy()
        self.forest = RandomForestRegressor(n_estimators=self.n_trees, max_features=0.3,
                                            min_samples_leaf=1, n_jobs=-1, random_state=self.seed)
        self.forest.fit(self.featurize(history), y)
        return self

    def predict(self, candidates):
        """Returns (mean, std) arrays, one value per candidate row."""
        X = self.featurize(candidates)
        per_tree = np.stack([t.predict(X) for t in self.forest.estimators_])
        return per_tree.mean(axis=0), per_tree.std(axis=0)
