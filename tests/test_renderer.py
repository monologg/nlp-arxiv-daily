"""Renderer tests.

Two layers:
1. Golden-fixture byte-equivalence — guards the README/gitpage/archive
   markdown against drift. Goldens were generated from master before the
   renderer was split; the new renderer must reproduce them byte-for-byte.
2. Decomposed helper tests — exercise the small private helpers in
   isolation so future tweaks fail loudly without needing a full re-render.
"""

import datetime
import shutil
from pathlib import Path

import pytest

from nlp_arxiv_daily.renderer import (
    _archive_link_line,
    _back_to_top_line,
    _badge_link_definitions,
    _badge_shields,
    _date_now_str,
    _jekyll_front_matter,
    _keyword_section,
    _title_line,
    _toc,
    pretty_math,
    render_archive_pages,
    render_index,
    sort_papers,
)


FIXTURE_DIR = Path(__file__).parent / "fixtures"
EXPECTED = FIXTURE_DIR / "expected"
TODAY = datetime.date(2026, 4, 26)


class TestGoldenReadme:
    def test_readme_flavor_matches_golden(self, tmp_path):
        out = tmp_path / "out.md"
        render_index(
            str(FIXTURE_DIR / "papers_sample.json"),
            str(out),
            task="golden",
            show_badge=True,
            user_name="alice",
            repo_name="my-repo",
            archive_index_link="docs/archive/index.md",
            today=TODAY,
        )
        assert out.read_text() == (EXPECTED / "readme.md").read_text()


class TestGoldenWeb:
    def test_web_flavor_matches_golden(self, tmp_path):
        out = tmp_path / "out.md"
        render_index(
            str(FIXTURE_DIR / "papers_sample_web.json"),
            str(out),
            task="golden",
            to_web=True,
            show_badge=False,
            user_name="alice",
            repo_name="my-repo",
            archive_index_link="archive-web/index.md",
            today=TODAY,
        )
        assert out.read_text() == (EXPECTED / "web.md").read_text()


class TestGoldenArchiveMonth:
    def test_archive_month_flavor_matches_golden(self, tmp_path):
        out = tmp_path / "out.md"
        render_index(
            str(FIXTURE_DIR / "papers_sample.json"),
            str(out),
            task="golden",
            show_badge=False,
            today=TODAY,
        )
        assert out.read_text() == (EXPECTED / "archive_month.md").read_text()


class TestGoldenArchivePages:
    def test_archive_pages_match_golden_dir(self, tmp_path):
        # Set up a tmp archive_src dir that mirrors the expected layout
        src = tmp_path / "src"
        src.mkdir()
        shutil.copy(FIXTURE_DIR / "papers_sample.json", src / "2026-03.json")
        shutil.copy(FIXTURE_DIR / "papers_sample.json", src / "2025-12.json")

        out_dir = tmp_path / "out"
        render_archive_pages(str(src), str(out_dir), today=TODAY)

        for name in ("2026-03.md", "2025-12.md", "index.md"):
            actual = (out_dir / name).read_text()
            expected = (EXPECTED / "archive_dir" / name).read_text()
            assert actual == expected, f"{name} drifted"


class TestSortPapers:
    def test_descending_keys(self):
        assert list(sort_papers({"2208.10000": "b", "2604.00001": "a", "2008.05000": "c"}).keys()) == [
            "2604.00001",
            "2208.10000",
            "2008.05000",
        ]

    def test_empty(self):
        assert sort_papers({}) == {}


class TestPrettyMath:
    def test_passthrough_when_no_math(self):
        assert pretty_math("plain text") == "plain text"

    def test_pads_inline_math_when_no_surrounding_space(self):
        out = pretty_math("foo$x+y$bar")
        assert out == "foo $x+y$ bar"

    def test_skips_padding_when_surrounded_by_space(self):
        out = pretty_math("foo $x+y$ bar")
        # inner whitespace stripped, outer preserved
        assert out == "foo $x+y$ bar"

    def test_skips_padding_when_surrounded_by_asterisk(self):
        out = pretty_math("**$x$**")
        assert out == "**$x$**"


class TestSmallHelpers:
    def test_date_now_str_dot_format(self):
        assert _date_now_str(datetime.date(2026, 4, 26)) == "2026.04.26"

    def test_jekyll_front_matter_constant(self):
        assert _jekyll_front_matter() == "---\nlayout: default\n---\n\n"

    def test_badge_shields_block_has_4_badges(self):
        out = _badge_shields()
        assert out.count("[![") == 4
        assert out.endswith("\n\n")

    def test_badge_link_definitions_use_repo_slug(self):
        out = _badge_link_definitions("alice/my-repo")
        assert "alice/my-repo" in out
        assert "github.com/alice/my-repo/graphs/contributors" in out

    def test_title_line_h2_when_use_title(self):
        assert _title_line("2026.04.26", use_title=True) == "## Updated on 2026.04.26\n\n"

    def test_title_line_blockquote_when_no_title(self):
        assert _title_line("2026.04.26", use_title=False) == "> Updated on 2026.04.26\n\n"

    def test_archive_link_line_empty_when_no_link(self):
        assert _archive_link_line("") == ""

    def test_archive_link_line_blockquote(self):
        assert _archive_link_line("docs/archive/index.md") == "> Older months: [archive](docs/archive/index.md)\n\n"

    def test_back_to_top_anchor_strips_dots_lowercases(self):
        out = _back_to_top_line("2026.04.26")
        assert "#updated-on-20260426" in out
        assert out.startswith("<p align=right>")

    def test_toc_skips_keywords_with_no_papers(self):
        data = {"NLP": {"2604.00001": "row"}, "Empty": {}}
        out = _toc(data)
        assert "<a href='#nlp'>NLP</a>" in out
        assert "Empty" not in out

    def test_toc_html_id_lowercases_and_dashes(self):
        data = {"Question Answering": {"2604.00001": "row"}}
        out = _toc(data)
        assert "<a href='#question-answering'>Question Answering</a>" in out


class TestKeywordSection:
    def test_readme_flavor_includes_table_header(self):
        out = _keyword_section(
            "NLP",
            {"2604.00001": "|row1|\n"},
            to_web=False,
            use_title=True,
            date_now="2026.04.26",
        )
        assert "|Publish Date|" in out
        assert "|---|" in out
        assert "|row1|" in out
        assert "<a href='#updated-on-20260426'>back to top</a>" in out

    def test_web_flavor_skips_table_header(self):
        out = _keyword_section(
            "NLP",
            {"2604.00001": "- bullet\n"},
            to_web=True,
            use_title=True,
            date_now="2026.04.26",
        )
        assert "Publish Date" not in out
        assert "|---|" not in out
        assert "- bullet" in out

    def test_rows_sorted_descending(self):
        out = _keyword_section(
            "NLP",
            {"2604.00001": "OLDER\n", "2604.00009": "NEWER\n"},
            to_web=True,
            use_title=False,
            date_now="2026.04.26",
        )
        assert out.index("NEWER") < out.index("OLDER")


@pytest.fixture(autouse=True)
def _cleanup_logging_basic_config():
    """The renderer logs a 'finished' message; nothing to clean up — placeholder."""
    yield
