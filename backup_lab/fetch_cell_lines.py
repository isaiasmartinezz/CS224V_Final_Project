"""Download cell-line genetics from Cell Model Passports (Wellcome Sanger; cellmodelpassports.sanger.ac.uk).
The DepMap portal blocks automated downloads (bot verification), so we use Sanger's public files instead.

Small files are saved as-is; the 1.2 GB expression file is streamed and only rows for our cell lines are kept.
Outputs in data/raw/cmp/ (not committed):
  model_list_latest.csv.gz, mutations_summary_latest.csv.gz (cancer-driver mutations per line),
  cnv_summary_latest.csv.gz, rnaseq_oneil_lines.csv (model_id, gene_symbol, rsem_tpm, data_source)

Usage: python -m backup_lab.fetch_cell_lines"""
import csv
import gzip
import io
from pathlib import Path

import requests

from backup_lab.cell_line_map import CMP_ID

BASE = "https://cog.sanger.ac.uk/cmp/download/"
OUT = Path("data/raw/cmp")
SMALL = ["model_list_latest.csv.gz", "mutations_summary_latest.csv.gz", "cnv_summary_latest.csv.gz"]
RNASEQ = "rnaseq_latest.csv.gz"


def download(name):
    path = OUT / name
    if path.exists():
        print(f"have {path}")
        return
    r = requests.get(BASE + name, timeout=120)
    r.raise_for_status()
    path.write_bytes(r.content)
    print(f"saved {path} ({len(r.content):,} bytes)")


def stream_rnaseq():
    out = OUT / "rnaseq_oneil_lines.csv"
    if out.exists():
        print(f"have {out}")
        return
    wanted = {i for i in CMP_ID.values() if i}
    tmp, n_seen, n_kept = out.with_suffix(".partial"), 0, 0
    with requests.get(BASE + RNASEQ, stream=True, timeout=120) as r, open(tmp, "w", newline="") as f:
        r.raise_for_status()
        r.raw.decode_content = False  # file itself is gzip; decompress below
        reader = csv.DictReader(io.TextIOWrapper(gzip.GzipFile(fileobj=r.raw), encoding="utf-8"))
        writer = csv.writer(f)
        writer.writerow(["model_id", "gene_symbol", "rsem_tpm", "data_source", "duplicate"])
        for row in reader:
            n_seen += 1
            if row["model_id"] in wanted:
                writer.writerow([row["model_id"], row["gene_symbol"], row["rsem_tpm"],
                                 row["data_source"], row["duplicate"]])
                n_kept += 1
            if n_seen % 5_000_000 == 0:
                print(f"  scanned {n_seen:,}, kept {n_kept:,}", flush=True)
    tmp.rename(out)
    print(f"rnaseq: scanned {n_seen:,} rows, kept {n_kept:,} -> {out}")


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for name in SMALL:
        download(name)
    stream_rnaseq()


if __name__ == "__main__":
    main()
