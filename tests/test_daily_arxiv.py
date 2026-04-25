import json
import os
import textwrap

import pytest
import requests

import daily_arxiv
from daily_arxiv import (
    bucket_by_month,
    find_code_link,
    get_authors,
    json_to_md,
    load_config,
    render_archive_pages,
    sort_papers,
    update_json_file,
    write_papers_split,
)


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


class TestJsonToMd:
    @pytest.fixture
    def json_file(self, tmp_path):
        path = tmp_path / "papers.json"
        path.write_text(json.dumps({"NLP": {"2208.10000": "|**2025-01-01**|**T**|A et.al.|[id](u)|null|\n"}}))
        return str(path)

    def test_truncates_existing_md_output(self, tmp_path, json_file):
        md_path = tmp_path / "README.md"
        md_path.write_text("STALE CONTENT FROM PRIOR RUN\n" * 100)
        json_to_md(json_file, str(md_path), show_badge=False)
        assert "STALE CONTENT" not in md_path.read_text()

    def test_badge_urls_use_configured_user_and_repo(self, tmp_path, json_file):
        md_path = tmp_path / "README.md"
        json_to_md(
            json_file,
            str(md_path),
            show_badge=True,
            user_name="alice",
            repo_name="my-proj",
        )
        rendered = md_path.read_text()
        assert "alice/my-proj" in rendered
        assert "monologg/nlp-arxiv-daily" not in rendered

    def test_archive_index_link_rendered_when_set(self, tmp_path, json_file):
        md_path = tmp_path / "README.md"
        json_to_md(
            json_file,
            str(md_path),
            show_badge=False,
            archive_index_link="docs/archive/index.md",
        )
        assert "docs/archive/index.md" in md_path.read_text()

    def test_archive_index_link_omitted_when_blank(self, tmp_path, json_file):
        md_path = tmp_path / "README.md"
        json_to_md(json_file, str(md_path), show_badge=False)
        assert "archive" not in md_path.read_text().lower()

    def test_to_web_omits_markdown_table_header(self, tmp_path):
        path = tmp_path / "papers.json"
        path.write_text(json.dumps({"NLP": {"2604.21637": "- 2026-04-22, **T**, A et.al., Paper: [u](u)\n"}}))
        md_path = tmp_path / "index.md"
        json_to_md(str(path), str(md_path), to_web=True, show_badge=False)
        rendered = md_path.read_text()
        assert "| Publish Date |" not in rendered
        assert "|:---------|" not in rendered
        assert "## NLP" in rendered
        assert "- 2026-04-22" in rendered


class TestBucketByMonth:
    def test_groups_by_yymm_prefix(self):
        papers = {
            "NLP": {
                "2604.00001": "row-april-26",
                "2603.00099": "row-march-26",
                "2208.10000": "row-aug-22",
            },
            "QA": {
                "2604.99999": "row-april-26-qa",
            },
        }
        out = bucket_by_month(papers)
        assert set(out.keys()) == {"2604", "2603", "2208"}
        assert out["2604"] == {
            "NLP": {"2604.00001": "row-april-26"},
            "QA": {"2604.99999": "row-april-26-qa"},
        }
        assert out["2603"] == {"NLP": {"2603.00099": "row-march-26"}}
        assert out["2208"] == {"NLP": {"2208.10000": "row-aug-22"}}

    def test_skips_unparseable_keys(self):
        papers = {"NLP": {"weird-key": "x", "2604.00001": "ok"}}
        out = bucket_by_month(papers)
        assert "2604" in out
        assert "weird-key" not in str(out)  # silently dropped
        for bucket in out.values():
            assert "weird-key" not in bucket.get("NLP", {})

    def test_empty_input(self):
        assert bucket_by_month({}) == {}

    def test_skips_keyword_with_no_papers(self):
        out = bucket_by_month({"NLP": {}, "QA": {"2604.00001": "x"}})
        assert out == {"2604": {"QA": {"2604.00001": "x"}}}


class TestWritePapersSplit:
    def _setup_paths(self, tmp_path):
        return {
            "main": str(tmp_path / "main.json"),
            "archive_dir": str(tmp_path / "archive"),
        }

    def test_first_run_no_existing_files(self, tmp_path):
        paths = self._setup_paths(tmp_path)
        write_papers_split(
            [{"NLP": {"2604.00001": "apr-row", "2603.00099": "mar-row"}}],
            paths["main"],
            paths["archive_dir"],
            current_yymm="2604",
        )
        assert json.loads(open(paths["main"]).read()) == {"NLP": {"2604.00001": "apr-row"}}
        assert json.loads(open(f"{paths['archive_dir']}/2026-03.json").read()) == {
            "NLP": {"2603.00099": "mar-row"},
        }

    def test_migrates_legacy_main_with_all_months(self, tmp_path):
        """Existing 5MB main JSON containing every month gets split."""
        paths = self._setup_paths(tmp_path)
        # Pretend the legacy main contains 3 months of data
        with open(paths["main"], "w") as f:
            json.dump(
                {
                    "NLP": {
                        "2604.00001": "apr",
                        "2603.00001": "mar",
                        "2208.00001": "aug22",
                    }
                },
                f,
            )
        write_papers_split([], paths["main"], paths["archive_dir"], current_yymm="2604")

        assert json.loads(open(paths["main"]).read()) == {"NLP": {"2604.00001": "apr"}}
        assert json.loads(open(f"{paths['archive_dir']}/2026-03.json").read()) == {
            "NLP": {"2603.00001": "mar"},
        }
        assert json.loads(open(f"{paths['archive_dir']}/2022-08.json").read()) == {
            "NLP": {"2208.00001": "aug22"},
        }

    def test_merges_new_daily_papers_into_existing(self, tmp_path):
        paths = self._setup_paths(tmp_path)
        with open(paths["main"], "w") as f:
            json.dump({"NLP": {"2604.00001": "old-apr"}}, f)
        write_papers_split(
            [{"NLP": {"2604.00002": "new-apr"}}],
            paths["main"],
            paths["archive_dir"],
            current_yymm="2604",
        )
        assert json.loads(open(paths["main"]).read()) == {
            "NLP": {"2604.00001": "old-apr", "2604.00002": "new-apr"},
        }

    def test_idempotent_re_bucket(self, tmp_path):
        """Running twice with same input produces same output (no drift)."""
        paths = self._setup_paths(tmp_path)
        new_papers = [{"NLP": {"2604.00001": "apr", "2603.00001": "mar"}}]
        write_papers_split(new_papers, paths["main"], paths["archive_dir"], current_yymm="2604")
        snapshot_main = open(paths["main"]).read()
        snapshot_archive = open(f"{paths['archive_dir']}/2026-03.json").read()

        write_papers_split([], paths["main"], paths["archive_dir"], current_yymm="2604")
        assert open(paths["main"]).read() == snapshot_main
        assert open(f"{paths['archive_dir']}/2026-03.json").read() == snapshot_archive

    def test_main_empty_when_no_current_month_papers(self, tmp_path):
        paths = self._setup_paths(tmp_path)
        write_papers_split(
            [{"NLP": {"2603.00001": "mar"}}],
            paths["main"],
            paths["archive_dir"],
            current_yymm="2604",  # no April papers
        )
        assert json.loads(open(paths["main"]).read()) == {}
        assert json.loads(open(f"{paths['archive_dir']}/2026-03.json").read()) == {
            "NLP": {"2603.00001": "mar"},
        }


class TestRenderArchivePages:
    def _seed_archives(self, tmp_path):
        archive_json_dir = tmp_path / "archive-json"
        archive_json_dir.mkdir()
        (archive_json_dir / "2026-03.json").write_text(
            json.dumps({"NLP": {"2603.00001": "|**2026-03-01**|**T1**|A et.al.|[id](u)|null|\n"}})
        )
        (archive_json_dir / "2025-12.json").write_text(
            json.dumps({"NLP": {"2512.00099": "|**2025-12-01**|**T2**|B et.al.|[id](u)|null|\n"}})
        )
        return str(archive_json_dir)

    def test_creates_one_md_per_archive_json(self, tmp_path):
        archive_json_dir = self._seed_archives(tmp_path)
        archive_md_dir = str(tmp_path / "archive-md")
        render_archive_pages(archive_json_dir, archive_md_dir)
        assert os.path.exists(f"{archive_md_dir}/2026-03.md")
        assert os.path.exists(f"{archive_md_dir}/2025-12.md")

    def test_archive_md_contains_month_papers(self, tmp_path):
        archive_json_dir = self._seed_archives(tmp_path)
        archive_md_dir = str(tmp_path / "archive-md")
        render_archive_pages(archive_json_dir, archive_md_dir)
        rendered = open(f"{archive_md_dir}/2026-03.md").read()
        assert "T1" in rendered
        assert "T2" not in rendered  # belongs to 2025-12.md

    def test_index_lists_months_descending(self, tmp_path):
        archive_json_dir = self._seed_archives(tmp_path)
        archive_md_dir = str(tmp_path / "archive-md")
        render_archive_pages(archive_json_dir, archive_md_dir)
        index = open(f"{archive_md_dir}/index.md").read()
        assert "2026-03" in index
        assert "2025-12" in index
        # 2026-03 must appear before 2025-12 (descending)
        assert index.index("2026-03") < index.index("2025-12")

    def test_no_op_when_archive_dir_missing(self, tmp_path):
        archive_md_dir = str(tmp_path / "archive-md")
        render_archive_pages(str(tmp_path / "does-not-exist"), archive_md_dir)
        assert not os.path.exists(archive_md_dir)
