"""Download the O'Neil 2016 screen from DrugComb v1.5 (Zenodo mirror; drugcomb.org was down Nov 9).

Streams the 1.4 GB summary file and keeps only rows with study_name == "ONEIL",
so the full file never sits on disk. Output: data/raw/drugcomb_oneil.csv (a few MB, not committed).

Source: DrugComb v1.5 summary_v_1_5.csv, https://zenodo.org/records/15235991
(md5 of the full file: cd3e24758c10ffaea0124b6e80626c32; Zheng et al. 2021, doi 10.1093/nar/gkab438)

Usage: python -m backup_lab.fetch_oneil"""
import csv
import io
from pathlib import Path

import requests

URL = "https://zenodo.org/records/15235991/files/summary_v_1_5.csv?download=1"
OUT = Path("data/raw/drugcomb_oneil.csv")
STUDY = "ONEIL"


def main():
    OUT.parent.mkdir(parents=True, exist_ok=True)
    tmp = OUT.with_suffix(".partial")
    n_seen = n_kept = 0
    with requests.get(URL, stream=True, timeout=60) as r, open(tmp, "w", newline="") as f:
        r.raise_for_status()
        r.raw.decode_content = True  # Zenodo sends it gzip-compressed
        lines = io.TextIOWrapper(r.raw, encoding="utf-8", newline="")
        reader = csv.reader(lines)
        header = next(reader)
        study_col = header.index("study_name")
        writer = csv.writer(f)
        writer.writerow(header)
        for row in reader:
            n_seen += 1
            if len(row) > study_col and row[study_col] == STUDY:
                writer.writerow(row)
                n_kept += 1
            if n_seen % 500_000 == 0:
                print(f"  scanned {n_seen:,} rows, kept {n_kept:,}", flush=True)
    tmp.rename(OUT)
    print(f"done: scanned {n_seen:,} rows, kept {n_kept:,} {STUDY} rows -> {OUT}")


if __name__ == "__main__":
    main()
