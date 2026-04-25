import datetime

import pytest

from nlp_arxiv_daily import fetcher
from nlp_arxiv_daily.fetcher import (
    _strip_version_suffix,
    fetch_papers,
    fetch_papers_in_range,
    get_authors,
)
from nlp_arxiv_daily.types import Paper


class _FakeArxivResult:
    def __init__(
        self,
        *,
        short_id: str,
        title: str = "A Title",
        authors: list[str] | None = None,
        updated: datetime.datetime | None = None,
        entry_id: str = "http://arxiv.org/abs/X",
        summary: str = "no code link here",
    ):
        self._short_id = short_id
        self.title = title
        self.authors = authors or ["Alice", "Bob"]
        self.updated = updated or datetime.datetime(2026, 4, 22, 0, 0, 0)
        self.entry_id = entry_id
        self.summary = summary

    def get_short_id(self):
        return self._short_id


class _FakeClient:
    def __init__(self, results):
        self._results = results

    def results(self, search):  # noqa: ARG002 — mirror real API signature
        return iter(self._results)


def _patch_arxiv(monkeypatch, results):
    """Patch arxiv with a single result list. Captures the last constructed
    Search and Client(...) kwargs on `fetcher._last_search` / `_last_client_kwargs`
    so tests can assert query / delay_seconds.
    """
    captured = {"search": None, "client_kwargs": None}

    def fake_client(**kwargs):
        captured["client_kwargs"] = kwargs
        return _FakeClient(results)

    monkeypatch.setattr(fetcher.arxiv, "Client", fake_client)

    class _FakeSearch:
        def __init__(self, query, max_results, sort_by):
            self.query = query
            self.max_results = max_results
            self.sort_by = sort_by
            captured["search"] = self

    monkeypatch.setattr(fetcher.arxiv, "Search", _FakeSearch)
    return captured


def _silence_code_link(monkeypatch):
    monkeypatch.setattr(fetcher, "find_code_link", lambda *args, **kw: None)


class TestStripVersionSuffix:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("2108.09112v1", "2108.09112"),
            ("2108.09112v23", "2108.09112"),
            ("2108.09112", "2108.09112"),  # no version
            ("2604.21637v1", "2604.21637"),
        ],
    )
    def test_strips_version(self, raw, expected):
        assert _strip_version_suffix(raw) == expected


class TestGetAuthors:
    def test_first_author(self):
        assert get_authors(["Alice", "Bob"], first_author=True) == "Alice"

    def test_join_all(self):
        assert get_authors(["Alice", "Bob"]) == "Alice, Bob"

    def test_casts_objects(self):
        class A:
            def __str__(self):
                return "X"

        assert get_authors([A(), A()]) == "X, X"


class TestFetchPapers:
    def test_returns_typed_paper_list(self, monkeypatch):
        _silence_code_link(monkeypatch)
        results = [
            _FakeArxivResult(
                short_id="2604.21637v1",
                title="Hello",
                authors=["Alice", "Bob"],
                updated=datetime.datetime(2026, 4, 22, 12, 0, 0),
                entry_id="http://arxiv.org/abs/2604.21637v1",
            )
        ]
        _patch_arxiv(monkeypatch, results)

        papers = fetch_papers(query="NLP", max_results=2)

        assert len(papers) == 1
        p = papers[0]
        assert isinstance(p, Paper)
        assert p.paper_id == "2604.21637"  # version stripped
        assert p.arxiv_short_id == "2604.21637v1"  # raw preserved
        assert p.title == "Hello"
        assert p.first_author == "Alice"
        assert p.update_time == datetime.date(2026, 4, 22)
        assert p.paper_url == "http://arxiv.org/abs/2604.21637v1"
        assert p.code_link is None

    def test_handles_empty_result_set(self, monkeypatch):
        _silence_code_link(monkeypatch)
        _patch_arxiv(monkeypatch, [])
        assert fetch_papers(query="NLP", max_results=2) == []

    def test_uses_versionless_id_for_code_link_lookup(self, monkeypatch):
        seen_ids = []

        def fake_find(arxiv_id, summary=None):  # noqa: ARG001
            seen_ids.append(arxiv_id)
            return None

        monkeypatch.setattr(fetcher, "find_code_link", fake_find)
        _patch_arxiv(monkeypatch, [_FakeArxivResult(short_id="2511.12345v3")])

        fetch_papers(query="x", max_results=1)
        # HF Papers API takes versionless ids — lookups must reflect that.
        assert seen_ids == ["2511.12345"]

    def test_propagates_code_link(self, monkeypatch):
        monkeypatch.setattr(fetcher, "find_code_link", lambda *args, **kw: "https://github.com/foo/bar")
        _patch_arxiv(monkeypatch, [_FakeArxivResult(short_id="2604.00001v1")])

        papers = fetch_papers(query="x", max_results=1)
        assert papers[0].code_link == "https://github.com/foo/bar"


class TestFetchPapersInRange:
    def test_builds_composite_query_with_submitted_date(self, monkeypatch):
        _silence_code_link(monkeypatch)
        captured = _patch_arxiv(monkeypatch, [])

        fetch_papers_in_range(
            query='NLPOR"Natural Language Processing"',
            start=datetime.date(2025, 8, 1),
            end=datetime.date(2025, 8, 31),
            max_results=500,
        )

        assert captured["search"] is not None
        q = captured["search"].query
        # Combined: keyword filter wrapped in parens AND submittedDate range.
        assert '(NLPOR"Natural Language Processing")' in q
        assert "submittedDate:[202508010000 TO 202508312359]" in q
        assert " AND " in q
        assert captured["search"].max_results == 500

    def test_uses_arxiv_client_with_rate_limit(self, monkeypatch):
        _silence_code_link(monkeypatch)
        captured = _patch_arxiv(monkeypatch, [])

        fetch_papers_in_range(
            query="NLP",
            start=datetime.date(2025, 8, 1),
            end=datetime.date(2025, 8, 31),
        )

        # arxiv.Client must be constructed with delay_seconds >= 3 to respect
        # the API's published 3s minimum between requests.
        kwargs = captured["client_kwargs"]
        assert kwargs is not None
        assert kwargs.get("delay_seconds", 0) >= 3

    def test_returns_typed_papers_for_in_range_results(self, monkeypatch):
        _silence_code_link(monkeypatch)
        results = [
            _FakeArxivResult(
                short_id="2508.00001v1",
                title="Aug paper",
                authors=["Alice"],
                updated=datetime.datetime(2025, 8, 15, 10, 0, 0),
                entry_id="http://arxiv.org/abs/2508.00001v1",
            )
        ]
        _patch_arxiv(monkeypatch, results)

        papers = fetch_papers_in_range(
            query="NLP",
            start=datetime.date(2025, 8, 1),
            end=datetime.date(2025, 8, 31),
        )
        assert len(papers) == 1
        p = papers[0]
        assert isinstance(p, Paper)
        assert p.paper_id == "2508.00001"
        assert p.update_time == datetime.date(2025, 8, 15)

    def test_default_max_results_is_high_for_backfill(self, monkeypatch):
        _silence_code_link(monkeypatch)
        captured = _patch_arxiv(monkeypatch, [])

        fetch_papers_in_range(
            query="NLP",
            start=datetime.date(2025, 8, 1),
            end=datetime.date(2025, 8, 31),
        )
        # The default should be high enough that a busy keyword for one month
        # doesn't get truncated. Daily fetch uses 10; backfill needs hundreds.
        assert captured["search"].max_results >= 1000

    def test_end_date_includes_full_day(self, monkeypatch):
        _silence_code_link(monkeypatch)
        captured = _patch_arxiv(monkeypatch, [])

        fetch_papers_in_range(
            query="NLP",
            start=datetime.date(2025, 8, 1),
            end=datetime.date(2025, 8, 31),
        )
        # Otherwise we miss anything submitted on the 31st after 00:00.
        assert "202508312359" in captured["search"].query


class TestGetDailyPapersAdapter:
    """get_daily_papers is the legacy markdown-row adapter on top of fetch_papers."""

    def test_renders_versioned_id_in_pdf_link(self, monkeypatch):
        from nlp_arxiv_daily import get_daily_papers

        _silence_code_link(monkeypatch)
        _patch_arxiv(
            monkeypatch,
            [
                _FakeArxivResult(
                    short_id="2604.21637v2",
                    title="T",
                    authors=["Alice"],
                    updated=datetime.datetime(2026, 4, 22),
                    entry_id="http://arxiv.org/abs/2604.21637v2",
                )
            ],
        )

        data, data_web = get_daily_papers("NLP", query="x", max_results=1)
        # README row keys by versionless id, but link text shows the full short id.
        assert "2604.21637" in data["NLP"]
        row = data["NLP"]["2604.21637"]
        assert "[2604.21637v2](http://arxiv.org/abs/2604.21637v2)" in row
        assert "|null|" in row  # no code link

        web_row = data_web["NLP"]["2604.21637"]
        assert web_row.startswith("- 2026-04-22, **T**, Alice et.al.")
        assert "Code:" not in web_row  # no code link

    def test_renders_code_link_when_present(self, monkeypatch):
        from nlp_arxiv_daily import get_daily_papers

        monkeypatch.setattr(fetcher, "find_code_link", lambda *args, **kw: "https://github.com/x/y")
        _patch_arxiv(
            monkeypatch,
            [_FakeArxivResult(short_id="2604.00001v1")],
        )

        data, data_web = get_daily_papers("NLP", query="x", max_results=1)
        row = data["NLP"]["2604.00001"]
        assert "**[link](https://github.com/x/y)**" in row
        web_row = data_web["NLP"]["2604.00001"]
        assert "Code: **[https://github.com/x/y](https://github.com/x/y)**" in web_row
