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

        monkeypatch.setattr(fetcher.arxiv, "Client", lambda: type("X", (), {"results": lambda self, s: iter([])})())

        class _FakeSearch:
            def __init__(self, *a, **kw):
                pass

        monkeypatch.setattr(fetcher.arxiv, "Search", _FakeSearch)
        cli.main(["--config_path", fake_config_file, "fetch"])


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
