import json

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
