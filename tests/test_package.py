import datetime

import pytest


class TestPackageImports:
    def test_top_level_package_exposes_public_api(self):
        import nlp_arxiv_daily as pkg

        for name in [
            "bucket_by_month",
            "find_code_link",
            "get_authors",
            "get_daily_papers",
            "json_to_md",
            "load_config",
            "render_archive_pages",
            "sort_papers",
            "update_json_file",
            "write_papers_split",
        ]:
            assert hasattr(pkg, name), f"nlp_arxiv_daily missing public symbol {name!r}"

    def test_legacy_shim_still_importable(self):
        # daily_arxiv.py is the cron entrypoint; tests import from it too.
        import daily_arxiv

        assert callable(daily_arxiv.find_code_link)
        # Required for monkeypatching `daily_arxiv.requests` in existing tests.
        assert hasattr(daily_arxiv, "requests")

    def test_shim_and_package_share_same_callables(self):
        import daily_arxiv
        import nlp_arxiv_daily

        assert daily_arxiv.find_code_link is nlp_arxiv_daily.find_code_link
        assert daily_arxiv.write_papers_split is nlp_arxiv_daily.write_papers_split


class TestTypes:
    def test_paper_dataclass_constructible(self):
        from nlp_arxiv_daily.types import Paper

        p = Paper(
            paper_id="2604.21637",
            title="A Title",
            first_author="Alice",
            update_time=datetime.date(2026, 4, 22),
            paper_url="http://arxiv.org/abs/2604.21637",
            code_link=None,
        )
        assert p.paper_id == "2604.21637"
        assert p.code_link is None

    def test_paper_is_frozen(self):
        from nlp_arxiv_daily.types import Paper

        p = Paper(
            paper_id="2604.21637",
            title="A",
            first_author="Alice",
            update_time=datetime.date(2026, 4, 22),
            paper_url="u",
            code_link=None,
        )
        with pytest.raises(Exception):  # FrozenInstanceError
            p.title = "B"  # type: ignore[misc]

    def test_keyword_config_is_typed_dict(self):
        from nlp_arxiv_daily.types import KeywordConfig

        # TypedDicts are dicts at runtime; constructibility is the contract.
        cfg: KeywordConfig = {"filters": ["NLP", "Natural Language Processing"]}
        assert cfg["filters"] == ["NLP", "Natural Language Processing"]

    def test_aliases_are_dict_at_runtime(self):
        from nlp_arxiv_daily.types import PapersByKeyword, PapersByMonth

        # Type aliases — runtime substitutability with dict is the contract.
        pbk: PapersByKeyword = {"NLP": {"2604.00001": "row"}}
        pbm: PapersByMonth = {"2604": {"NLP": {"2604.00001": "row"}}}
        assert pbk["NLP"]["2604.00001"] == "row"
        assert pbm["2604"]["NLP"]["2604.00001"] == "row"
