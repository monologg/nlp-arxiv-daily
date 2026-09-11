import json
import pathlib

from nlp_arxiv_daily import storage
from nlp_arxiv_daily.storage import (
    _current_yymm,
    _yymm_to_archive_basename,
    bucket_by_month,
    write_papers_split,
)


class TestYymmHelpers:
    def test_yymm_to_archive_basename(self):
        assert _yymm_to_archive_basename("2604") == "2026-04"
        assert _yymm_to_archive_basename("9912") == "2099-12"
        assert _yymm_to_archive_basename("0001") == "2000-01"

    def test_current_yymm_format(self):
        v = _current_yymm()
        assert len(v) == 4
        assert v.isdigit()


class TestBucketByMonthEdgeCases:
    """Complementary to TestBucketByMonth in test_daily_arxiv.py."""

    def test_two_keywords_same_paper_id_kept_separately(self):
        # Same paper indexed under two keywords stays under both buckets/keywords
        papers = {
            "NLP": {"2604.00001": "row-nlp"},
            "QA": {"2604.00001": "row-qa"},
        }
        out = bucket_by_month(papers)
        assert out["2604"]["NLP"]["2604.00001"] == "row-nlp"
        assert out["2604"]["QA"]["2604.00001"] == "row-qa"

    def test_5digit_paper_id_bucketed(self):
        # arxiv supports both 4- and 5-digit paper numbers; both are valid
        papers = {"NLP": {"2604.12345": "row"}}
        out = bucket_by_month(papers)
        assert out == {"2604": {"NLP": {"2604.12345": "row"}}}


class TestWritePapersSplitRoundTrip:
    def _seed(self, tmp_path):
        return {
            "main": str(tmp_path / "main.json"),
            "archive_dir": str(tmp_path / "archive"),
        }

    def test_multi_month_byte_stable_across_reruns(self, tmp_path):
        """Re-running with empty new_papers_list must not drift any file."""
        paths = self._seed(tmp_path)
        write_papers_split(
            [
                {
                    "NLP": {
                        "2604.00001": "apr",
                        "2603.00099": "mar",
                        "2208.10000": "aug22",
                    },
                    "QA": {
                        "2604.00099": "apr-qa",
                        "2208.99999": "aug22-qa",
                    },
                }
            ],
            paths["main"],
            paths["archive_dir"],
            current_yymm="2604",
        )

        # Snapshot every file
        all_paths = [
            paths["main"],
            f"{paths['archive_dir']}/2026-03.json",
            f"{paths['archive_dir']}/2022-08.json",
        ]
        snapshots = {p: open(p).read() for p in all_paths}

        # Re-run idempotently
        write_papers_split([], paths["main"], paths["archive_dir"], current_yymm="2604")

        for p in all_paths:
            assert open(p).read() == snapshots[p], f"{p} drifted across reruns"

    def test_late_arriving_paper_merges_into_old_archive(self, tmp_path):
        """A paper from an archived month must merge into the right archive file."""
        paths = self._seed(tmp_path)
        # Seed: April current, March archive
        write_papers_split(
            [{"NLP": {"2604.00001": "apr-old", "2603.00001": "mar-old"}}],
            paths["main"],
            paths["archive_dir"],
            current_yymm="2604",
        )
        # Daily fetch returns a March paper that wasn't in the archive
        write_papers_split(
            [{"NLP": {"2603.00002": "mar-new"}}],
            paths["main"],
            paths["archive_dir"],
            current_yymm="2604",
        )
        march = json.loads(open(f"{paths['archive_dir']}/2026-03.json").read())
        assert march == {"NLP": {"2603.00001": "mar-old", "2603.00002": "mar-new"}}
        # April main is untouched by the late-arriving March paper
        april = json.loads(open(paths["main"]).read())
        assert april == {"NLP": {"2604.00001": "apr-old"}}

    def test_archive_file_unchanged_when_no_new_paper_in_that_month(self, tmp_path):
        """An archive file's content must be identical after a re-run that
        only adds papers to the current month."""
        paths = self._seed(tmp_path)
        # Seed two months
        write_papers_split(
            [{"NLP": {"2604.00001": "apr", "2603.00001": "mar"}}],
            paths["main"],
            paths["archive_dir"],
            current_yymm="2604",
        )
        march_before = open(f"{paths['archive_dir']}/2026-03.json").read()

        # Add only a new April paper
        write_papers_split(
            [{"NLP": {"2604.00002": "apr-new"}}],
            paths["main"],
            paths["archive_dir"],
            current_yymm="2604",
        )
        march_after = open(f"{paths['archive_dir']}/2026-03.json").read()
        assert march_before == march_after

    def test_keyword_added_later_does_not_lose_old_archive_data(self, tmp_path):
        """When a NEW keyword first appears, existing archive files for OTHER
        keywords must not be wiped — re-bucketing reads the whole archive."""
        paths = self._seed(tmp_path)
        write_papers_split(
            [{"NLP": {"2603.00001": "mar"}}],
            paths["main"],
            paths["archive_dir"],
            current_yymm="2604",
        )
        # Add a new keyword for current month only
        write_papers_split(
            [{"QA": {"2604.00001": "apr-qa"}}],
            paths["main"],
            paths["archive_dir"],
            current_yymm="2604",
        )
        march = json.loads(open(f"{paths['archive_dir']}/2026-03.json").read())
        # NLP March data must still be there
        assert march == {"NLP": {"2603.00001": "mar"}}

    def test_overwrite_in_same_month_takes_latest_value(self, tmp_path):
        """Same paper id submitted twice — the second value wins (revision)."""
        paths = self._seed(tmp_path)
        write_papers_split(
            [{"NLP": {"2604.00001": "v1"}}],
            paths["main"],
            paths["archive_dir"],
            current_yymm="2604",
        )
        write_papers_split(
            [{"NLP": {"2604.00001": "v2"}}],
            paths["main"],
            paths["archive_dir"],
            current_yymm="2604",
        )
        main = json.loads(open(paths["main"]).read())
        assert main == {"NLP": {"2604.00001": "v2"}}

    def test_keyword_order_reorders_main_and_archive_keys(self, tmp_path):
        """Astro site reads JSON keys in insertion order — write_papers_split must
        emit keys per `keyword_order` so config.yaml is the source of truth."""
        paths = self._seed(tmp_path)
        # Seed in NLP, QA order
        write_papers_split(
            [{"NLP": {"2604.00001": "apr", "2603.00001": "mar"}, "QA": {"2604.00099": "apr-qa"}}],
            paths["main"],
            paths["archive_dir"],
            current_yymm="2604",
        )
        # Re-run with reversed order; data is unchanged but key order should follow
        write_papers_split(
            [],
            paths["main"],
            paths["archive_dir"],
            current_yymm="2604",
            keyword_order=["QA", "NLP"],
        )
        main_keys = list(json.loads(open(paths["main"]).read()).keys())
        archive_keys = list(json.loads(open(f"{paths['archive_dir']}/2026-03.json").read()).keys())
        assert main_keys == ["QA", "NLP"]
        # March archive only has NLP — no crash, unknown keys (none here) shouldn't appear
        assert archive_keys == ["NLP"]

    def test_keyword_order_appends_unknown_keywords(self, tmp_path):
        """Keys present in the JSON but missing from `keyword_order` must still
        be emitted, after the ordered ones — never dropped."""
        paths = self._seed(tmp_path)
        write_papers_split(
            [{"NLP": {"2604.00001": "a"}, "Surprise": {"2604.00002": "b"}}],
            paths["main"],
            paths["archive_dir"],
            current_yymm="2604",
            keyword_order=["NLP"],  # "Surprise" not in config
        )
        main = json.loads(open(paths["main"]).read())
        assert list(main.keys()) == ["NLP", "Surprise"]


class TestWebRecordsStorage:
    def test_dict_values_round_trip_and_override_strings(self, tmp_path):
        """A re-fetched paper arrives as a dict and must replace its old
        string row for the same id; untouched string rows survive as-is."""
        main = tmp_path / "main.json"
        archive = tmp_path / "archive"
        main.write_text(
            json.dumps(
                {
                    "NLP": {
                        "2604.00001": "- 2026-04-21, **Old**, A et.al., Paper: [u](u)\n",
                        "2604.00002": "- 2026-04-22, **Keep**, B et.al., Paper: [u](u)\n",
                    }
                }
            )
        )
        record = {
            "date": "2026-04-21",
            "title": "Old",
            "authors": ["A", "Z"],
            "url": "u",
            "code": None,
            "abstract": "abs",
            "categories": [],
        }
        write_papers_split([{"NLP": {"2604.00001": record}}], str(main), str(archive), current_yymm="2604")
        out = json.loads(main.read_text())
        assert out["NLP"]["2604.00001"] == record
        assert out["NLP"]["2604.00002"].startswith("- 2026-04-22, **Keep**")


class TestLoadKnownCodeLinks:
    def test_collects_ids_and_links_across_main_and_archive(self, tmp_path):
        from nlp_arxiv_daily.storage import load_known_code_links

        main = tmp_path / "main.json"
        archive = tmp_path / "archive"
        archive.mkdir()
        main.write_text(
            json.dumps(
                {
                    "NLP": {
                        "2609.00001": {
                            "date": "2026-09-01",
                            "title": "A",
                            "authors": ["x"],
                            "url": "u",
                            "code": "https://github.com/a/a",
                            "abstract": "",
                            "categories": [],
                        },
                        "2609.00002": "- 2026-09-02, **B**, y et.al., Paper: [u](u)\n",
                    }
                }
            )
        )
        (archive / "2026-08.json").write_text(
            json.dumps(
                {
                    "LLM": {
                        "2608.00009": "- 2026-08-09, **C**, z et.al., Paper: [u](u), Code: **[https://github.com/c/c](https://github.com/c/c)**\n"
                    }
                }
            )
        )
        known = load_known_code_links(str(main), str(archive))
        assert known == {
            "2609.00001": "https://github.com/a/a",
            "2609.00002": None,
            "2608.00009": "https://github.com/c/c",
        }

    def test_missing_files_give_empty(self, tmp_path):
        from nlp_arxiv_daily.storage import load_known_code_links

        assert load_known_code_links(str(tmp_path / "nope.json"), str(tmp_path / "nodir")) == {}


class TestFillCodeLinks:
    """A code-link lookup that failed mid-run persists as `code: null`, which
    is indistinguishable from "HF has no repo for this paper" — and because
    the id is then `known`, no later backfill re-asks. Filling them back in
    needs a targeted, id-driven write."""

    def _tree(self, tmp_path):
        archive = tmp_path / "archive"
        archive.mkdir()
        main = tmp_path / "main.json"
        main.write_text(
            json.dumps(
                {
                    "LLM": {
                        "2601.00001": {"date": "2026-01-02", "title": "a", "authors": ["A"], "url": "u", "code": None},
                        "2601.00002": {"date": "2026-01-03", "title": "b", "authors": ["B"], "url": "u", "code": None},
                    }
                }
            )
        )
        (archive / "2025-06.json").write_text(
            json.dumps(
                {
                    "LLM": {
                        "2506.00001": {"date": "2025-06-02", "title": "c", "authors": ["C"], "url": "u", "code": None},
                        "2506.00009": {
                            "date": "2025-06-04",
                            "title": "kept",
                            "authors": ["D"],
                            "url": "u",
                            "code": "http://github.com/keep/me",
                        },
                    },
                    # The same paper under a second keyword must be filled too.
                    "RAG": {
                        "2506.00001": {"date": "2025-06-02", "title": "c", "authors": ["C"], "url": "u", "code": None},
                    },
                }
            )
        )
        (archive / "2019-04.json").write_text(
            json.dumps({"NLP": {"1904.00001": "- 2019-04-01, **legacy**, X et.al., Paper: [u](u)\n"}})
        )
        return str(main), str(archive)

    def test_fills_only_the_requested_ids(self, tmp_path):
        main, archive = self._tree(tmp_path)
        n = storage.fill_code_links(main, archive, {"2601.00001": "http://github.com/o/r"})
        assert n == 1
        got = json.loads(pathlib.Path(main).read_text())
        assert got["LLM"]["2601.00001"]["code"] == "http://github.com/o/r"
        assert got["LLM"]["2601.00002"]["code"] is None

    def test_fills_every_keyword_holding_the_paper(self, tmp_path):
        main, archive = self._tree(tmp_path)
        n = storage.fill_code_links(main, archive, {"2506.00001": "http://github.com/o/r"})
        assert n == 2
        got = json.loads((pathlib.Path(archive) / "2025-06.json").read_text())
        assert got["LLM"]["2506.00001"]["code"] == "http://github.com/o/r"
        assert got["RAG"]["2506.00001"]["code"] == "http://github.com/o/r"

    def test_never_overwrites_a_link_already_stored(self, tmp_path):
        main, archive = self._tree(tmp_path)
        n = storage.fill_code_links(main, archive, {"2506.00009": "http://github.com/other/repo"})
        assert n == 0
        got = json.loads((pathlib.Path(archive) / "2025-06.json").read_text())
        assert got["LLM"]["2506.00009"]["code"] == "http://github.com/keep/me"

    def test_legacy_string_rows_are_left_alone(self, tmp_path):
        main, archive = self._tree(tmp_path)
        before = (pathlib.Path(archive) / "2019-04.json").read_text()
        assert storage.fill_code_links(main, archive, {"1904.00001": "http://github.com/o/r"}) == 0
        assert (pathlib.Path(archive) / "2019-04.json").read_text() == before

    def test_untouched_files_are_not_rewritten(self, tmp_path):
        main, archive = self._tree(tmp_path)
        target = pathlib.Path(archive) / "2019-04.json"
        mtime = target.stat().st_mtime_ns
        storage.fill_code_links(main, archive, {"2601.00001": "http://github.com/o/r"})
        assert target.stat().st_mtime_ns == mtime
