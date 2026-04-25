import textwrap

import pytest

from daily_arxiv import get_authors, load_config, sort_papers


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
