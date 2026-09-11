"""CLI dispatch tests.

The hard guarantee: `render`-only must NOT make network calls (it only reads
persisted JSON), and `fetch`-only must NOT touch markdown. The cron path
(`run`) calls both in order.
"""

from __future__ import annotations

import datetime
import textwrap

import pytest

from nlp_arxiv_daily import cli


@pytest.fixture
def fake_config_file(tmp_path):
    json_dir = tmp_path / "docs"
    json_dir.mkdir()
    archive_dir = json_dir / "archive"
    archive_web_dir = json_dir / "archive-web"
    archive_dir.mkdir()
    archive_web_dir.mkdir()
    # Empty JSON files so render() has something to read
    (json_dir / "main.json").write_text("{}")
    (json_dir / "main-web.json").write_text("{}")

    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        textwrap.dedent(
            f"""
            user_name: "alice"
            repo_name: "my-repo"
            show_authors: true
            show_links: true
            show_badge: false
            max_results: 1
            publish_readme: true
            publish_gitpage: true
            json_readme_path: "{json_dir / "main.json"}"
            json_gitpage_path: "{json_dir / "main-web.json"}"
            md_readme_path: "{tmp_path / "README.md"}"
            md_gitpage_path: "{json_dir / "index.md"}"
            archive_readme_json_dir: "{archive_dir}"
            archive_readme_md_dir: "{archive_dir}"
            archive_gitpage_json_dir: "{archive_web_dir}"
            archive_gitpage_md_dir: "{archive_web_dir}"
            keywords:
              "NLP":
                filters: ["NLP"]
            """
        ).strip()
    )
    return str(cfg)


class TestArgparser:
    def test_no_subcommand_defaults_to_run(self):
        ns = cli.build_parser().parse_args([])
        assert ns.command is None  # main() coerces to "run"

    def test_subcommands_recognized(self):
        for sub in ("run", "fetch", "render"):
            ns = cli.build_parser().parse_args([sub])
            assert ns.command == sub

    def test_config_path_default(self):
        ns = cli.build_parser().parse_args([])
        assert ns.config_path == "config.yaml"

    def test_config_path_override(self):
        ns = cli.build_parser().parse_args(["--config_path", "x.yaml", "fetch"])
        assert ns.config_path == "x.yaml"


class TestDispatch:
    def test_main_no_subcommand_dispatches_run(self, monkeypatch, fake_config_file):
        called = []
        monkeypatch.setattr(cli, "cmd_run", lambda config: called.append(("run", config)))
        cli.main(["--config_path", fake_config_file])
        assert len(called) == 1
        assert called[0][0] == "run"

    def test_main_render_dispatches_render(self, monkeypatch, fake_config_file):
        called = []
        monkeypatch.setattr(cli, "cmd_render", lambda config: called.append(("render", config)))
        cli.main(["--config_path", fake_config_file, "render"])
        assert called and called[0][0] == "render"

    def test_main_fetch_dispatches_fetch(self, monkeypatch, fake_config_file):
        called = []
        monkeypatch.setattr(cli, "cmd_fetch", lambda config: called.append(("fetch", config)))
        cli.main(["--config_path", fake_config_file, "fetch"])
        assert called and called[0][0] == "fetch"


class TestCommandIsolation:
    """Behavioral isolation: render MUST NOT fetch, fetch MUST NOT render."""

    def test_render_does_not_fetch(self, monkeypatch, fake_config_file):
        def boom(*a, **kw):
            raise AssertionError("render must not call fetch_papers / get_daily_papers")

        monkeypatch.setattr("nlp_arxiv_daily.fetcher.fetch_papers", boom)
        monkeypatch.setattr("nlp_arxiv_daily.core.get_daily_papers", boom)
        # render against an empty JSON config — should produce empty markdown only
        cli.main(["--config_path", fake_config_file, "render"])

    def test_fetch_does_not_render(self, monkeypatch, fake_config_file):
        def boom(*a, **kw):
            raise AssertionError("fetch must not call json_to_md / render_archive_pages")

        monkeypatch.setattr("nlp_arxiv_daily.cli.json_to_md", boom)
        monkeypatch.setattr("nlp_arxiv_daily.cli.render_archive_pages", boom)

        # Mock fetch_papers so no network
        from nlp_arxiv_daily import fetcher

        monkeypatch.setattr(
            fetcher.arxiv,
            "Client",
            lambda **_kw: type("X", (), {"results": lambda self, s: iter([])})(),
        )

        class _FakeSearch:
            def __init__(self, *a, **kw):
                pass

        monkeypatch.setattr(fetcher.arxiv, "Search", _FakeSearch)
        cli.main(["--config_path", fake_config_file, "fetch"])


class TestCmdFetchResilience:
    """A single keyword's arxiv failure (e.g. a 429/503 storm) must not kill
    the whole daily run — the surviving keywords still get persisted."""

    def _config(self, tmp_path):
        json_dir = tmp_path / "docs"
        json_dir.mkdir(exist_ok=True)
        archive_web_dir = json_dir / "archive-web"
        archive_web_dir.mkdir(exist_ok=True)
        (json_dir / "main-web.json").write_text("{}")
        return {
            "kv": {"NLP": "NLP", "LLM": "LLM"},
            "max_results": 1,
            "publish_readme": False,
            "publish_gitpage": True,
            "json_gitpage_path": str(json_dir / "main-web.json"),
            "archive_gitpage_json_dir": str(archive_web_dir),
        }

    @staticmethod
    def _paper(topic):
        # YYMM prefix must match the current month so it lands in main-web.json
        # (not the archive). bucket_by_month buckets by the id's YYMM prefix.
        import datetime

        from nlp_arxiv_daily.types import Paper

        today = datetime.date.today()
        key = f"{today.year % 100:02d}{today.month:02d}.00001"
        return Paper(
            paper_id=key,
            title=f"{topic} paper",
            first_author="A",
            update_time=today,
            paper_url=f"http://arxiv.org/abs/{key}v1",
            code_link=None,
            arxiv_short_id=f"{key}v1",
        )

    def test_one_keyword_failure_does_not_abort_run(self, monkeypatch, tmp_path):
        import json

        import arxiv

        def fake_fetch_recent(query, **kw):
            if query == "NLP":
                raise arxiv.HTTPError("https://export.arxiv.org/api/query", 1, 429)
            return [self._paper(query)]

        monkeypatch.setattr(cli, "fetch_recent_papers", fake_fetch_recent)

        config = self._config(tmp_path)
        # Must not raise even though NLP keyword 429s.
        cli.cmd_fetch(config)

        # The surviving keyword (LLM) was still persisted.
        written = json.loads((tmp_path / "docs" / "main-web.json").read_text())
        assert "LLM" in written
        assert "NLP" not in written

    def test_all_keywords_failing_raises(self, monkeypatch, tmp_path):
        import arxiv

        def boom(query, **kw):
            raise arxiv.HTTPError("https://export.arxiv.org/api/query", 1, 503)

        monkeypatch.setattr(cli, "fetch_recent_papers", boom)

        with pytest.raises(RuntimeError, match="all .* keyword fetches failed"):
            cli.cmd_fetch(self._config(tmp_path))


class TestCmdFetchWindow:
    """The daily fetch is a date-range query (last N days), not a top-N —
    a top-10 cap silently dropped ~90% of high-volume keywords (2026-09)."""

    def test_passes_lookback_cap_and_known_links(self, monkeypatch, tmp_path):
        import json

        json_dir = tmp_path / "docs"
        json_dir.mkdir()
        archive_web_dir = json_dir / "archive-web"
        archive_web_dir.mkdir()
        (json_dir / "main-web.json").write_text(
            json.dumps(
                {
                    "NLP": {
                        "2609.00001": "- 2026-09-01, **Old**, A et.al., Paper: [u](u), Code: **[https://github.com/o/o](https://github.com/o/o)**\n"
                    }
                }
            )
        )
        config = {
            "kv": {"NLP": "all:NLP"},
            "max_results": 1000,
            "daily_lookback_days": 5,
            "publish_readme": False,
            "publish_gitpage": True,
            "json_gitpage_path": str(json_dir / "main-web.json"),
            "archive_gitpage_json_dir": str(archive_web_dir),
        }
        calls = []

        def fake_fetch_recent(query, **kw):
            calls.append((query, kw))
            return []

        monkeypatch.setattr(cli, "fetch_recent_papers", fake_fetch_recent)
        cli.cmd_fetch(config)
        assert len(calls) == 1
        query, kw = calls[0]
        assert query == "all:NLP"
        assert kw["lookback_days"] == 5
        assert kw["max_results"] == 1000
        assert kw["known_code_links"] == {"2609.00001": "https://github.com/o/o"}

    def test_lookback_defaults_when_config_omits_it(self, monkeypatch, tmp_path):
        json_dir = tmp_path / "docs"
        json_dir.mkdir()
        (json_dir / "main-web.json").write_text("{}")
        config = {
            "kv": {"NLP": "all:NLP"},
            "max_results": 1000,
            "publish_readme": False,
            "publish_gitpage": True,
            "json_gitpage_path": str(json_dir / "main-web.json"),
            "archive_gitpage_json_dir": str(json_dir / "archive-web"),
        }
        seen = {}
        monkeypatch.setattr(cli, "fetch_recent_papers", lambda query, **kw: seen.update(kw) or [])
        cli.cmd_fetch(config)
        from nlp_arxiv_daily.fetcher import DEFAULT_DAILY_LOOKBACK_DAYS

        assert seen["lookback_days"] == DEFAULT_DAILY_LOOKBACK_DAYS


class TestCmdRunInvocation:
    def test_run_calls_fetch_then_render_in_order(self, monkeypatch, fake_config_file):
        order = []
        monkeypatch.setattr(cli, "cmd_fetch", lambda config: order.append("fetch"))
        monkeypatch.setattr(cli, "cmd_render", lambda config: order.append("render"))
        cli.main(["--config_path", fake_config_file, "run"])
        assert order == ["fetch", "render"]


class TestParseYyyyMm:
    def test_parses_valid_yyyy_mm(self):
        assert cli._parse_yyyy_mm("2025-08") == datetime.date(2025, 8, 1)

    @pytest.mark.parametrize("bad", ["", "2025", "2025-13-01", "abc-08", "2025/08"])
    def test_rejects_invalid(self, bad):
        with pytest.raises(Exception):
            cli._parse_yyyy_mm(bad)


class TestIterMonthRanges:
    def test_single_month(self):
        ranges = list(cli._iter_month_ranges(datetime.date(2025, 8, 1), datetime.date(2025, 8, 1)))
        assert ranges == [(datetime.date(2025, 8, 1), datetime.date(2025, 8, 31))]

    def test_year_boundary(self):
        # Dec 2025 → Feb 2026
        ranges = list(cli._iter_month_ranges(datetime.date(2025, 12, 1), datetime.date(2026, 2, 1)))
        assert [m[0] for m in ranges] == [
            datetime.date(2025, 12, 1),
            datetime.date(2026, 1, 1),
            datetime.date(2026, 2, 1),
        ]
        assert ranges[0][1] == datetime.date(2025, 12, 31)
        assert ranges[1][1] == datetime.date(2026, 1, 31)
        assert ranges[2][1] == datetime.date(2026, 2, 28)

    def test_normalizes_mid_month_inputs(self):
        # _parse_yyyy_mm always emits day=1, but the helper should still cope
        # with mid-month inputs by clamping to month boundaries.
        ranges = list(cli._iter_month_ranges(datetime.date(2025, 8, 17), datetime.date(2025, 9, 5)))
        assert [m[0] for m in ranges] == [
            datetime.date(2025, 8, 1),
            datetime.date(2025, 9, 1),
        ]


class TestBackfillDispatch:
    def test_backfill_with_explicit_end_invokes_cmd_backfill(self, monkeypatch, fake_config_file):
        captured = {}

        def fake(config, *, start, end, max_results, **_):
            captured["start"] = start
            captured["end"] = end
            captured["max_results"] = max_results

        monkeypatch.setattr(cli, "cmd_backfill", fake)
        cli.main(
            [
                "--config_path",
                fake_config_file,
                "backfill",
                "--start",
                "2025-08",
                "--end",
                "2026-03",
            ]
        )
        assert captured["start"] == datetime.date(2025, 8, 1)
        assert captured["end"] == datetime.date(2026, 3, 1)
        # Backfill default must NOT inherit config["max_results"] (which is the
        # daily-fetch top-N cap of ~10) — it ignores config and uses the
        # backfill-appropriate ceiling from fetcher.BACKFILL_DEFAULT_MAX_RESULTS.
        assert captured["max_results"] >= 1000

    def test_backfill_default_end_is_current_month(self, monkeypatch, fake_config_file):
        captured = {}
        monkeypatch.setattr(
            cli,
            "cmd_backfill",
            lambda config, *, start, end, max_results, **_: captured.setdefault("end", end),
        )
        # Pin "today" so the test is deterministic.
        monkeypatch.setattr(cli, "_current_month_first", lambda: datetime.date(2026, 4, 1))
        cli.main(["--config_path", fake_config_file, "backfill", "--start", "2025-08"])
        assert captured["end"] == datetime.date(2026, 4, 1)

    def test_backfill_max_results_override(self, monkeypatch, fake_config_file):
        captured = {}
        monkeypatch.setattr(
            cli,
            "cmd_backfill",
            lambda config, *, start, end, max_results, **_: captured.setdefault("max_results", max_results),
        )
        cli.main(
            [
                "--config_path",
                fake_config_file,
                "backfill",
                "--start",
                "2025-08",
                "--max-results",
                "50",
            ]
        )
        assert captured["max_results"] == 50

    def test_backfill_requires_start(self, fake_config_file):
        with pytest.raises(SystemExit):
            cli.main(["--config_path", fake_config_file, "backfill"])


class TestIterWindows:
    """A month can be split into fixed-size windows so a busy keyword (LLM is
    2,000+/month) is not truncated by the per-query result cap."""

    def test_none_is_the_whole_month(self):
        assert cli._iter_windows(datetime.date(2025, 8, 1), datetime.date(2025, 8, 31), None) == [
            (datetime.date(2025, 8, 1), datetime.date(2025, 8, 31))
        ]

    def test_seven_day_windows_clip_at_month_end(self):
        got = cli._iter_windows(datetime.date(2025, 8, 1), datetime.date(2025, 8, 31), 7)
        assert got == [
            (datetime.date(2025, 8, 1), datetime.date(2025, 8, 7)),
            (datetime.date(2025, 8, 8), datetime.date(2025, 8, 14)),
            (datetime.date(2025, 8, 15), datetime.date(2025, 8, 21)),
            (datetime.date(2025, 8, 22), datetime.date(2025, 8, 28)),
            (datetime.date(2025, 8, 29), datetime.date(2025, 8, 31)),
        ]

    def test_window_longer_than_month_is_the_whole_month(self):
        assert cli._iter_windows(datetime.date(2026, 2, 1), datetime.date(2026, 2, 28), 45) == [
            (datetime.date(2026, 2, 1), datetime.date(2026, 2, 28))
        ]


class TestBackfillWindows:
    def _config(self, tmp_path):
        json_dir = tmp_path / "docs"
        json_dir.mkdir()
        (json_dir / "archive-web").mkdir()
        (json_dir / "main-web.json").write_text("{}")
        return {
            "kv": {"LLM": "all:LLM"},
            "publish_readme": False,
            "publish_gitpage": True,
            "json_gitpage_path": str(json_dir / "main-web.json"),
            "archive_gitpage_json_dir": str(json_dir / "archive-web"),
            "show_badge": False,
            "user_name": "u",
            "repo_name": "r",
        }

    @staticmethod
    def _paper(pid, day):
        from nlp_arxiv_daily.types import Paper

        return Paper(
            paper_id=pid,
            title=pid,
            first_author="A",
            update_time=datetime.date(2025, 8, day),
            paper_url=f"http://arxiv.org/abs/{pid}v1",
            code_link=None,
            arxiv_short_id=f"{pid}v1",
        )

    def test_windows_are_fetched_separately_and_merged(self, monkeypatch, tmp_path):
        import json

        calls = []

        def fake_fetch(query, start, end, **kw):
            calls.append((start, end))
            # Same paper returned by two neighbouring windows must be stored once.
            return (
                [self._paper("2508.00001", 7)]
                if start.day == 1
                else [self._paper("2508.00001", 7), self._paper(f"2508.{start.day:05d}", start.day)]
            )

        monkeypatch.setattr(cli, "fetch_papers_in_range", fake_fetch)
        monkeypatch.setattr(cli, "cmd_render", lambda config: None)
        config = self._config(tmp_path)
        cli.cmd_backfill(config, start=datetime.date(2025, 8, 1), end=datetime.date(2025, 8, 1), window_days=10)

        assert [(s.day, e.day) for s, e in calls] == [(1, 10), (11, 20), (21, 30), (31, 31)]
        written = json.loads((tmp_path / "docs" / "archive-web" / "2025-08.json").read_text())
        assert set(written["LLM"]) == {"2508.00001", "2508.00011", "2508.00021", "2508.00031"}

    def test_warns_when_a_window_hits_the_result_cap(self, monkeypatch, tmp_path, caplog):
        monkeypatch.setattr(
            cli,
            "fetch_papers_in_range",
            lambda query, start, end, **kw: [self._paper("2508.00001", 1), self._paper("2508.00002", 2)],
        )
        monkeypatch.setattr(cli, "cmd_render", lambda config: None)
        with caplog.at_level("WARNING"):
            cli.cmd_backfill(
                self._config(tmp_path), start=datetime.date(2025, 8, 1), end=datetime.date(2025, 8, 1), max_results=2
            )
        assert any("cap" in r.message and "LLM" in r.message for r in caplog.records)

    def test_no_warning_below_cap(self, monkeypatch, tmp_path, caplog):
        monkeypatch.setattr(
            cli, "fetch_papers_in_range", lambda query, start, end, **kw: [self._paper("2508.00001", 1)]
        )
        monkeypatch.setattr(cli, "cmd_render", lambda config: None)
        with caplog.at_level("WARNING"):
            cli.cmd_backfill(
                self._config(tmp_path), start=datetime.date(2025, 8, 1), end=datetime.date(2025, 8, 1), max_results=2
            )
        assert not any("cap" in r.message for r in caplog.records)

    def test_cli_passes_window_days(self, monkeypatch, fake_config_file):
        captured = {}
        monkeypatch.setattr(cli, "cmd_backfill", lambda config, **kw: captured.update(kw))
        cli.main(["--config_path", fake_config_file, "backfill", "--start", "2025-08", "--window-days", "7"])
        assert captured["window_days"] == 7

    def test_cli_window_days_defaults_to_none(self, monkeypatch, fake_config_file):
        captured = {}
        monkeypatch.setattr(cli, "cmd_backfill", lambda config, **kw: captured.update(kw))
        cli.main(["--config_path", fake_config_file, "backfill", "--start", "2025-08"])
        assert captured["window_days"] is None


class TestBackfillSharedClient:
    """The arxiv library's rate limiter lives on the client, so the backfill
    has to reuse one across queries. A fresh client per query only spaces the
    *pages* of a single query, which leaves `--delay-seconds` doing nothing
    for keywords that fit in one page."""

    def _config(self, tmp_path):
        json_dir = tmp_path / "docs"
        json_dir.mkdir()
        (json_dir / "archive-web").mkdir()
        (json_dir / "main-web.json").write_text("{}")
        return {
            "kv": {"LLM": "all:LLM", "NLP": "all:NLP"},
            "publish_readme": False,
            "publish_gitpage": True,
            "json_gitpage_path": str(json_dir / "main-web.json"),
            "archive_gitpage_json_dir": str(json_dir / "archive-web"),
            "show_badge": False,
            "user_name": "u",
            "repo_name": "r",
        }

    def _run(self, monkeypatch, tmp_path, **kw):
        clients = []

        def fake_fetch(query, start, end, **kwargs):
            clients.append(kwargs.get("client"))
            return []

        monkeypatch.setattr(cli, "fetch_papers_in_range", fake_fetch)
        monkeypatch.setattr(cli, "cmd_render", lambda config: None)
        cli.cmd_backfill(
            self._config(tmp_path),
            start=datetime.date(2025, 8, 1),
            end=datetime.date(2025, 9, 1),
            **kw,
        )
        return clients

    def test_one_client_is_shared_by_every_query(self, monkeypatch, tmp_path):
        clients = self._run(monkeypatch, tmp_path, window_days=15)
        # 2 keywords × (August: 1-15, 16-30, 31 + September: 1-15, 16-30)
        assert len(clients) == 10
        assert all(c is not None for c in clients)
        assert len({id(c) for c in clients}) == 1

    def test_client_is_built_with_the_requested_delay(self, monkeypatch, tmp_path):
        captured = {}

        def fake_make(delay_seconds):
            captured["delay_seconds"] = delay_seconds
            return object()

        monkeypatch.setattr(cli, "make_backfill_client", fake_make)
        self._run(monkeypatch, tmp_path, delay_seconds=15)
        assert captured["delay_seconds"] == 15


class TestCmdRecheckCodeLinks:
    """`recheck-code-links` re-asks HuggingFace for papers whose lookup failed
    during a run and were persisted with `code: null`."""

    def _config(self, tmp_path):
        json_dir = tmp_path / "docs"
        json_dir.mkdir()
        (json_dir / "archive-web").mkdir()
        (json_dir / "main-web.json").write_text("{}")
        return {
            "kv": {"LLM": "all:LLM"},
            "publish_readme": False,
            "publish_gitpage": True,
            "json_gitpage_path": str(json_dir / "main-web.json"),
            "archive_gitpage_json_dir": str(json_dir / "archive-web"),
            "show_badge": False,
            "user_name": "u",
            "repo_name": "r",
        }

    def test_looks_up_each_id_and_writes_what_it_finds(self, monkeypatch, tmp_path):
        looked = []
        monkeypatch.setattr(
            cli, "find_code_link", lambda pid, summary=None: (looked.append(pid), f"http://github.com/o/{pid}")[1]
        )
        written = {}
        monkeypatch.setattr(cli, "fill_code_links", lambda m, a, links: written.update(links) or len(links))
        cli.cmd_recheck_code_links(self._config(tmp_path), ids=["2601.00001", "2601.00002"])
        assert looked == ["2601.00001", "2601.00002"]
        assert written == {
            "2601.00001": "http://github.com/o/2601.00001",
            "2601.00002": "http://github.com/o/2601.00002",
        }

    def test_ids_without_a_link_are_not_written(self, monkeypatch, tmp_path):
        monkeypatch.setattr(cli, "find_code_link", lambda pid, summary=None: None)
        written = {}
        monkeypatch.setattr(cli, "fill_code_links", lambda m, a, links: written.update(links) or len(links))
        cli.cmd_recheck_code_links(self._config(tmp_path), ids=["2601.00001"])
        assert written == {}

    def test_a_failing_lookup_does_not_abort_the_rest(self, monkeypatch, tmp_path):
        def flaky(pid, summary=None):
            if pid == "bad":
                raise RuntimeError("HF down")
            return "http://github.com/o/r"

        monkeypatch.setattr(cli, "find_code_link", flaky)
        written = {}
        monkeypatch.setattr(cli, "fill_code_links", lambda m, a, links: written.update(links) or len(links))
        cli.cmd_recheck_code_links(self._config(tmp_path), ids=["bad", "2601.00002"])
        assert list(written) == ["2601.00002"]

    def test_dry_run_writes_nothing(self, monkeypatch, tmp_path):
        monkeypatch.setattr(cli, "find_code_link", lambda pid, summary=None: "http://github.com/o/r")
        calls = []
        monkeypatch.setattr(cli, "fill_code_links", lambda m, a, links: calls.append(links) or 0)
        cli.cmd_recheck_code_links(self._config(tmp_path), ids=["2601.00001"], dry_run=True)
        assert calls == []


class TestRecheckIdSources:
    def test_ids_from_a_log_file(self, tmp_path):
        log = tmp_path / "run.log"
        log.write_text(
            "[09/10/2026 19:39:58 WARNING] HF Papers lookup failed for 2302.09127: 429 Client Error\n"
            "[09/10/2026 19:40:07 INFO] Time = 2025-04-30 title = something\n"
            "[09/10/2026 19:50:02 WARNING] HF Papers lookup failed for 2305.17198: 429 Client Error\n"
            "[09/10/2026 19:51:02 WARNING] HF Papers lookup failed for 2302.09127: 429 Client Error\n"
        )
        assert cli._ids_from_log(str(log)) == ["2302.09127", "2305.17198"]

    def test_cli_passes_ids_and_dry_run(self, monkeypatch, fake_config_file):
        captured = {}
        monkeypatch.setattr(cli, "cmd_recheck_code_links", lambda config, **kw: captured.update(kw))
        cli.main(["--config_path", fake_config_file, "recheck-code-links", "--ids", "2601.1, 2601.2", "--dry-run"])
        assert captured == {"ids": ["2601.1", "2601.2"], "dry_run": True}
