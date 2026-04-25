import json
import textwrap

import pytest
import requests

import daily_arxiv
from daily_arxiv import find_code_link, get_authors, load_config, sort_papers, update_json_file


class TestGetAuthors:
    def test_returns_first_author_when_flag_set(self):
        authors = ["Alice", "Bob", "Charlie"]
        assert get_authors(authors, first_author=True) == "Alice"

    def test_joins_all_authors_with_comma(self):
        authors = ["Alice", "Bob", "Charlie"]
        assert get_authors(authors) == "Alice, Bob, Charlie"

    def test_single_author(self):
        assert get_authors(["Alice"]) == "Alice"
        assert get_authors(["Alice"], first_author=True) == "Alice"

    def test_casts_non_string_authors(self):
        class Author:
            def __init__(self, name):
                self.name = name

            def __str__(self):
                return self.name

        authors = [Author("Alice"), Author("Bob")]
        assert get_authors(authors) == "Alice, Bob"


class TestSortPapers:
    def test_sorts_keys_in_descending_order(self):
        papers = {"2108.09112": "a", "2208.10000": "b", "2008.05000": "c"}
        result = sort_papers(papers)
        assert list(result.keys()) == ["2208.10000", "2108.09112", "2008.05000"]

    def test_preserves_values(self):
        papers = {"2108.09112": "alpha", "2208.10000": "beta"}
        result = sort_papers(papers)
        assert result["2108.09112"] == "alpha"
        assert result["2208.10000"] == "beta"

    def test_empty_dict(self):
        assert sort_papers({}) == {}


class TestLoadConfig:
    @pytest.fixture
    def config_file(self, tmp_path):
        path = tmp_path / "config.yaml"
        path.write_text(
            textwrap.dedent(
                """
                base_url: "https://example.com/"
                user_name: "monologg"
                repo_name: "nlp-arxiv-daily"
                show_authors: true
                show_links: true
                show_badge: false
                max_results: 10
                publish_readme: true
                publish_gitpage: true
                json_readme_path: "./docs/a.json"
                json_gitpage_path: "./docs/b.json"
                md_readme_path: "README.md"
                md_gitpage_path: "./docs/index.md"
                keywords:
                  "NLP":
                    filters: ["NLP", "Natural Language Processing"]
                  "QA":
                    filters: ["QA"]
                """
            ).strip()
        )
        return str(path)

    def test_loads_top_level_keys(self, config_file):
        config = load_config(config_file)
        assert config["max_results"] == 10
        assert config["user_name"] == "monologg"

    def test_quotes_multi_word_filters(self, config_file):
        config = load_config(config_file)
        assert config["kv"]["NLP"] == 'NLPOR"Natural Language Processing"'

    def test_single_word_filter_left_unquoted(self, config_file):
        config = load_config(config_file)
        assert config["kv"]["QA"] == "QA"


class _FakeResponse:
    def __init__(self, status_code: int, payload: dict | None = None):
        self.status_code = status_code
        self._payload = payload or {}

    def json(self):
        return self._payload


class TestFindCodeLink:
    def _patch_get(self, monkeypatch, *, status_code=200, payload=None, raises=None):
        calls = []

        def fake_get(url, timeout=None):
            calls.append(url)
            if raises is not None:
                raise raises
            return _FakeResponse(status_code, payload)

        monkeypatch.setattr(daily_arxiv.requests, "get", fake_get)
        return calls

    def test_returns_hf_github_repo_when_present(self, monkeypatch):
        self._patch_get(monkeypatch, payload={"githubRepo": "https://github.com/foo/bar"})
        assert find_code_link("2307.09288") == "https://github.com/foo/bar"

    def test_falls_back_to_summary_regex_when_hf_has_no_repo(self, monkeypatch):
        self._patch_get(monkeypatch, payload={"title": "...", "githubRepo": None})
        summary = "Code is available at https://github.com/acme/proj for reproducibility."
        assert find_code_link("2604.21637", summary=summary) == "https://github.com/acme/proj"

    def test_falls_back_to_summary_regex_on_404(self, monkeypatch):
        self._patch_get(monkeypatch, status_code=404, payload={"error": "not found"})
        summary = "See https://github.com/acme/proj."
        assert find_code_link("9999.00000", summary=summary) == "https://github.com/acme/proj"

    def test_falls_back_to_summary_regex_on_network_error(self, monkeypatch):
        self._patch_get(monkeypatch, raises=requests.ConnectionError("dns"))
        summary = "Repo: https://github.com/acme/proj"
        assert find_code_link("2604.21637", summary=summary) == "https://github.com/acme/proj"

    def test_returns_none_when_nothing_matches(self, monkeypatch):
        self._patch_get(monkeypatch, status_code=404)
        assert find_code_link("9999.00000", summary="No code link here.") is None

    def test_returns_none_when_summary_missing_and_hf_empty(self, monkeypatch):
        self._patch_get(monkeypatch, payload={})
        assert find_code_link("2604.21637") is None

    def test_strips_trailing_punctuation_from_summary_url(self, monkeypatch):
        self._patch_get(monkeypatch, status_code=404)
        summary = "We release code at https://github.com/acme/proj)."
        assert find_code_link("9999.00000", summary=summary) == "https://github.com/acme/proj"


class TestUpdateJsonFile:
    def test_creates_file_on_first_run_when_missing(self, tmp_path):
        path = tmp_path / "papers.json"
        update_json_file(str(path), [{"NLP": {"2208.10000": "row"}}])
        assert json.loads(path.read_text()) == {"NLP": {"2208.10000": "row"}}

    def test_treats_empty_file_as_empty_dict(self, tmp_path):
        path = tmp_path / "papers.json"
        path.write_text("")
        update_json_file(str(path), [{"NLP": {"2208.10000": "row"}}])
        assert json.loads(path.read_text()) == {"NLP": {"2208.10000": "row"}}

    def test_merges_into_existing_keyword(self, tmp_path):
        path = tmp_path / "papers.json"
        path.write_text(json.dumps({"NLP": {"2108.09112": "old"}}))
        update_json_file(str(path), [{"NLP": {"2208.10000": "new"}}])
        assert json.loads(path.read_text()) == {
            "NLP": {"2108.09112": "old", "2208.10000": "new"},
        }
