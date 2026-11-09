"""Offline tests for agent/retrieval.py: a fake PubMed stands in for the network."""
import json

import pytest

from agent import retrieval


def paper(pmid, title="A study", abstract="Some findings.", doi=""):
    return {"source_id": f"PMID:{pmid}", "pmid": pmid, "title": title, "abstract": abstract,
            "year": "2020", "doi": doi, "journal": "J"}


def article_xml(p):
    return (f"<PubmedArticle><MedlineCitation><PMID>{p['pmid']}</PMID><Article>"
            f"<Journal><Title>J</Title><JournalIssue><PubDate><Year>2020</Year></PubDate></JournalIssue></Journal>"
            f"<ArticleTitle>{p['title']}</ArticleTitle><Abstract><AbstractText>{p['abstract']}</AbstractText>"
            f"</Abstract></Article></MedlineCitation><PubmedData><ArticleIdList>"
            f"<ArticleId IdType=\"doi\">{p['doi']}</ArticleId></ArticleIdList></PubmedData></PubmedArticle>")


@pytest.fixture
def fake_pubmed(monkeypatch, tmp_path):
    """Serves the given papers for any query and counts network calls."""
    calls = []
    state = {"papers": []}

    def fake_get(endpoint, params):
        calls.append(endpoint)
        if endpoint == "esearch.fcgi":
            return json.dumps({"esearchresult": {"idlist": [p["pmid"] for p in state["papers"]]}})
        return "<PubmedArticleSet>" + "".join(article_xml(p) for p in state["papers"]) + "</PubmedArticleSet>"

    monkeypatch.setattr(retrieval, "_get", fake_get)
    monkeypatch.setattr(retrieval, "CACHE_DIR", tmp_path)
    return state, calls


def test_oneil_paper_is_in_the_real_exclusion_list():
    rules = retrieval.load_exclusions()
    assert "26983881" in rules["pmid"]
    assert retrieval.is_excluded(paper("1", doi="10.1158/1535-7163.MCT-15-0843"), rules)


@pytest.mark.parametrize("p", [
    paper("26983881"),
    paper("2", abstract="We used the O'Neil screen of 583 combinations."),
    paper("3", title="Deep learning for drug synergy prediction"),
    paper("4", abstract="Data were taken from DrugComb."),
    paper("5", abstract="Results from the Merck combination screen."),
])
def test_search_drops_excluded_sources(fake_pubmed, p):
    state, _ = fake_pubmed
    state["papers"] = [p, paper("99", title="PARP inhibitors trap PARP on DNA")]
    assert [x["pmid"] for x in retrieval.search("q")] == ["99"]


def test_search_drops_empty_abstracts_and_repeat_editions(fake_pubmed):
    state, _ = fake_pubmed
    state["papers"] = [paper("1", title="Lapatinib."), paper("2", title="Lapatinib."),
                       paper("3", abstract=""), paper("4", title="Other")]
    assert [x["pmid"] for x in retrieval.search("q")] == ["1", "4"]


def test_repeat_search_uses_cache(fake_pubmed):
    state, calls = fake_pubmed
    state["papers"] = [paper("1")]
    first = retrieval.search("veliparib")
    n_calls = len(calls)
    state["papers"] = []  # if the network were hit again, results would change
    assert retrieval.search("veliparib") == first
    assert len(calls) == n_calls == 2  # one esearch + one efetch, only the first time
