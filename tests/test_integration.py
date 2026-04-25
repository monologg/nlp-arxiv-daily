import arxiv
import pytest

from daily_arxiv import get_daily_papers


pytestmark = pytest.mark.integration


def test_arxiv_search_smoke():
    """arxiv API가 응답하고 Result 객체가 우리가 사용하는 필드를 모두 노출하는지."""
    client = arxiv.Client()
    search = arxiv.Search(
        query="NLP",
        max_results=2,
        sort_by=arxiv.SortCriterion.SubmittedDate,
    )
    results = list(client.results(search))

    assert len(results) > 0, "arxiv returned no results for query='NLP'"

    for r in results:
        assert r.title
        assert r.entry_id
        assert r.authors and len(r.authors) > 0
        assert r.updated is not None
        assert r.published is not None
        assert r.primary_category
        assert r.get_short_id()


def test_get_daily_papers_end_to_end():
    """get_daily_papers가 arxiv + HF Papers 호출을 거쳐 markdown 라인을 생성하는지."""
    data, data_web = get_daily_papers("NLP", query="NLP", max_results=2)

    assert "NLP" in data
    assert "NLP" in data_web

    papers = data["NLP"]
    web_papers = data_web["NLP"]

    assert len(papers) > 0, "get_daily_papers returned 0 entries"
    assert set(papers.keys()) == set(web_papers.keys())

    for line in papers.values():
        assert line.startswith("|**"), f"unexpected row prefix: {line!r}"
        assert "et.al." in line
        assert "|[link](" in line or "|null|" in line

    for line in web_papers.values():
        assert line.startswith("- ")
        assert "et.al." in line
        assert "Paper: [" in line
