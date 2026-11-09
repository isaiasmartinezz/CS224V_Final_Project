"""Literature retrieval from PubMed (placeholder until SHELDON access).

search(query) returns papers (title, abstract, year, DOI). Every raw response is cached
to data/cache/pubmed/, and excluded sources (agent/excluded_sources.txt) are filtered
on every read, so changing the exclusion list takes effect without re-downloading.

Usage: python -m agent.retrieval "veliparib" "carboplatin"   (prints evidence for a pair)"""
import hashlib
import json
import os
import re
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path

import pandas as pd
import requests
from dotenv import load_dotenv

load_dotenv()
EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
API_KEY = os.getenv("NCBI_API_KEY")
DELAY = 0.11 if API_KEY else 0.34  # NCBI limits: 10 requests/s with a key, 3 without
CACHE_DIR = Path("data/cache/pubmed")
EXCLUDED_FILE = Path(__file__).with_name("excluded_sources.txt")
ANNOTATIONS = Path("data/drug_annotations.csv")


# ---------- exclusion ----------

def load_exclusions(path=EXCLUDED_FILE):
    rules = {"pmid": set(), "doi": set(), "pattern": []}
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):  # comments go on their own lines
            continue
        kind, value = (s.strip() for s in line.split(":", 1))
        if kind == "pattern":
            rules["pattern"].append(re.compile(value, re.IGNORECASE))
        else:
            rules[kind].add(value.lower())
    return rules


def is_excluded(paper, rules):
    if paper["pmid"] in rules["pmid"] or paper["doi"].lower() in rules["doi"]:
        return True
    text = f"{paper['title']} {paper['abstract']}"
    return any(p.search(text) for p in rules["pattern"])


# ---------- PubMed calls (cached) ----------

def _get(endpoint, params):
    params = {**params, "db": "pubmed", "tool": "cancer-combo-agent"}
    if API_KEY:
        params["api_key"] = API_KEY
    for attempt in range(3):
        time.sleep(DELAY * (attempt + 1))
        try:
            r = requests.get(f"{EUTILS}/{endpoint}", params=params, timeout=30)
            if r.ok:
                return r.text
        except requests.RequestException:
            pass
    raise RuntimeError(f"PubMed {endpoint} failed after 3 tries: {params.get('term') or params.get('id')}")


def _parse_articles(xml_text):
    papers = []
    for art in ET.fromstring(xml_text).iter("PubmedArticle"):
        pmid = art.findtext(".//PMID", "")
        abstract = " ".join("".join(t.itertext()) for t in art.iter("AbstractText"))
        year = art.findtext(".//PubDate/Year") or (art.findtext(".//PubDate/MedlineDate") or "")[:4]
        doi = next((i.text or "" for i in art.iter("ArticleId") if i.get("IdType") == "doi"), "")
        papers.append({
            "source_id": f"PMID:{pmid}",
            "pmid": pmid,
            "title": "".join(art.find(".//ArticleTitle").itertext()) if art.find(".//ArticleTitle") is not None else "",
            "abstract": abstract,
            "year": year,
            "doi": doi,
            "journal": art.findtext(".//Journal/Title", ""),
        })
    return papers


def _cached_search(query, n):
    key = hashlib.sha1(f"{query}|{n}|relevance".encode()).hexdigest()[:16]
    path = CACHE_DIR / f"{key}.json"
    if path.exists():
        return json.loads(path.read_text())["papers"]
    # PubMed's API defaults to newest first; relevance gives far better results for well-studied drugs
    ids = json.loads(_get("esearch.fcgi", {"term": query, "retmax": n, "retmode": "json",
                                           "sort": "relevance"}))
    ids = ids["esearchresult"]["idlist"]
    papers = _parse_articles(_get("efetch.fcgi", {"id": ",".join(ids), "retmode": "xml"})) if ids else []
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"query": query, "n": n, "fetched": time.strftime("%Y-%m-%d"),
                                "papers": papers}, indent=1))
    return papers


def search(query, max_results=10):
    """Papers matching a PubMed query, most relevant first, with excluded sources removed."""
    rules = load_exclusions()
    papers = _cached_search(query, max_results + 10)  # over-fetch so exclusions don't shrink results
    kept, titles = [], set()
    for p in papers:
        title = re.sub(r"\W+", " ", p["title"].lower()).strip()
        # No abstract: nothing to reason from. Repeated title: another edition of the same review.
        if p["abstract"] and title not in titles and not is_excluded(p, rules):
            kept.append(p)
            titles.add(title)
    return kept[:max_results]


# ---------- evidence for the agent ----------

def _drug_term(drug, field="tiab"):
    """PubMed term matching the dataset name or the common name (e.g. ABT-888 or veliparib)."""
    names = {drug}
    if ANNOTATIONS.exists():
        ann = pd.read_csv(ANNOTATIONS, dtype=str).set_index("drug")
        if drug in ann.index:
            names.add(ann.at[drug, "search_name"])
    return "(" + " OR ".join(f'"{n}"[{field}]' for n in sorted(names)) + ")"


def evidence_for_drug(drug, n=5):
    """Mechanism papers for one drug. Title matches first, so famous drugs don't return
    passing mentions; abstract matches top up rare drugs that are seldom named in titles."""
    mech = '(mechanism[tiab] OR "mode of action"[tiab] OR inhibitor[tiab] OR target[tiab])'
    papers = search(f"{_drug_term(drug, 'ti')} AND {mech} AND cancer[tiab]", n)
    if len(papers) < n:
        seen = {p["pmid"] for p in papers}
        extra = search(f"{_drug_term(drug)} AND {mech}", n)
        papers += [p for p in extra if p["pmid"] not in seen][:n - len(papers)]
    return papers


def evidence_for_pair(drug_a, drug_b, per_query=5):
    """Short source lists: each drug's mechanism, and any paper on the two together."""
    return {
        "drug_a": evidence_for_drug(drug_a, per_query),
        "drug_b": evidence_for_drug(drug_b, per_query),
        "pair": search(f"{_drug_term(drug_a)} AND {_drug_term(drug_b)}", per_query),
    }


if __name__ == "__main__":
    ev = evidence_for_pair(*sys.argv[1:3])
    for part, papers in ev.items():
        print(f"\n== {part}: {len(papers)} sources")
        for p in papers:
            print(f"  {p['source_id']} ({p['year']}) {p['title'][:100]}")
