"""End-to-end pipeline test.

Wires fetch → storage → render together exactly like the cron does, but with
a mocked arxiv.Client (no network) and a temporary config + workspace.
Verifies the cross-cutting invariants no individual unit test catches:
- markdown + JSON files land at the configured paths
- multi-month results land in current/archive splits correctly
- archive index lists every month
- a paper from a past month gets bucketed into the right archive file
"""

from __future__ import annotations

import datetime
import json
import textwrap
from pathlib import Path

import pytest

from nlp_arxiv_daily import cli, fetcher


class _FakeArxivResult:
    def __init__(self, *, short_id, title, updated, entry_id, summary="no code"):
        self._short_id = short_id
        self.title = title
        self.authors = ["Alice"]
        self.updated = updated
        self.entry_id = entry_id
        self.summary = summary

    def get_short_id(self):
        return self._short_id


class _FakeClient:
    def __init__(self, results_by_query):
        self._results_by_query = results_by_query

    def results(self, search):
        return iter(self._results_by_query.get(search.query, []))


@pytest.fixture
def workspace(tmp_path):
    """Create a complete config + dir layout the CLI expects."""
    docs = tmp_path / "docs"
    archive = docs / "archive"
    archive_web = docs / "archive-web"
    docs.mkdir()
    archive.mkdir()
    archive_web.mkdir()

    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        textwrap.dedent(
            f"""
            user_name: "alice"
            repo_name: "my-repo"
            show_authors: true
            show_links: true
            show_badge: false
            max_results: 5
            publish_readme: true
            publish_gitpage: true
            json_readme_path: "{docs / "main.json"}"
            json_gitpage_path: "{docs / "main-web.json"}"
            md_readme_path: "{tmp_path / "README.md"}"
            md_gitpage_path: "{docs / "index.md"}"
            archive_readme_json_dir: "{archive}"
            archive_readme_md_dir: "{archive}"
            archive_gitpage_json_dir: "{archive_web}"
            archive_gitpage_md_dir: "{archive_web}"
            keywords:
              "NLP":
                filters: ["NLP"]
            """
        ).strip()
    )
    return {
        "config": str(cfg),
        "docs": docs,
        "archive": archive,
        "archive_web": archive_web,
        "readme": tmp_path / "README.md",
        "index": docs / "index.md",
        "main_json": docs / "main.json",
        "main_web_json": docs / "main-web.json",
    }


def _patch_arxiv(monkeypatch, results_by_query):
    monkeypatch.setattr(fetcher.arxiv, "Client", lambda: _FakeClient(results_by_query))

    class _FakeSearch:
        def __init__(self, query, max_results, sort_by):
            self.query = query
            self.max_results = max_results
            self.sort_by = sort_by

    monkeypatch.setattr(fetcher.arxiv, "Search", _FakeSearch)
    # Skip HF Papers / GitHub URL lookups — keeps the test deterministic
    monkeypatch.setattr(fetcher, "find_code_link", lambda *a, **kw: None)


class TestEndToEndPipeline:
    def test_fetch_render_cycle_produces_all_artifacts(self, monkeypatch, workspace):
        """Full pipeline: arxiv (mocked) → JSON splits → markdown for both
        README and gitpage flavors → archive index, with multi-month bucketing."""
        # Today is in April 2026; results span Apr 2026 (current) + Mar 2026 + Aug 2025
        results = [
            _FakeArxivResult(
                short_id="2604.00001v1",
                title="April Paper",
                updated=datetime.datetime(2026, 4, 22, 12, 0, 0),
                entry_id="http://arxiv.org/abs/2604.00001v1",
            ),
            _FakeArxivResult(
                short_id="2603.00099v1",
                title="March Paper",
                updated=datetime.datetime(2026, 3, 15, 8, 0, 0),
                entry_id="http://arxiv.org/abs/2603.00099v1",
            ),
            _FakeArxivResult(
                short_id="2508.12345v2",
                title="August Paper",
                updated=datetime.datetime(2025, 8, 5, 18, 0, 0),
                entry_id="http://arxiv.org/abs/2508.12345v2",
            ),
        ]
        _patch_arxiv(monkeypatch, {"NLP": results})

        # Force "today" through the storage current_yymm, since the renderer's
        # date-now is purely cosmetic ("Updated on YYYY.MM.DD") and doesn't
        # affect bucketing.
        from nlp_arxiv_daily import storage

        monkeypatch.setattr(storage, "_current_yymm", lambda: "2604")

        rc = cli.main(["--config_path", workspace["config"], "run"])
        assert rc == 0

        # JSON splits: current month in main, older months in archive
        main_json = json.loads(Path(workspace["main_json"]).read_text())
        assert "NLP" in main_json
        assert "2604.00001" in main_json["NLP"]
        # March + August must NOT be in the current-month main
        assert "2603.00099" not in main_json["NLP"]
        assert "2508.12345" not in main_json["NLP"]

        march_archive = json.loads((workspace["archive"] / "2026-03.json").read_text())
        assert "2603.00099" in march_archive["NLP"]

        aug_archive = json.loads((workspace["archive"] / "2025-08.json").read_text())
        assert "2508.12345" in aug_archive["NLP"]

        # Same split semantics for the gitpage (web) flavor
        web_json = json.loads(Path(workspace["main_web_json"]).read_text())
        assert "2604.00001" in web_json["NLP"]
        web_march = json.loads((workspace["archive_web"] / "2026-03.json").read_text())
        assert "2603.00099" in web_march["NLP"]

        # Markdown was written for README + gitpage
        readme = workspace["readme"].read_text()
        assert "## NLP" in readme
        assert "April Paper" in readme
        # README's main page only shows current month
        assert "March Paper" not in readme
        assert "August Paper" not in readme
        # Versioned id appears in the link text
        assert "[2604.00001v1](http://arxiv.org/abs/2604.00001v1)" in readme

        index = workspace["index"].read_text()
        assert index.startswith("---\nlayout: default\n---")
        assert "April Paper" in index
        assert "March Paper" not in index

        # Archive month markdown has the older paper
        march_md = (workspace["archive"] / "2026-03.md").read_text()
        assert "March Paper" in march_md
        aug_md = (workspace["archive"] / "2025-08.md").read_text()
        assert "August Paper" in aug_md

        # Archive index lists every month, descending
        archive_index = (workspace["archive"] / "index.md").read_text()
        assert archive_index.index("2026-03") < archive_index.index("2025-08")

    def test_fetch_then_render_separately_matches_run(self, monkeypatch, workspace):
        """`fetch` followed by `render` must produce the same artifacts as `run`."""
        results = [
            _FakeArxivResult(
                short_id="2604.00001v1",
                title="Paper A",
                updated=datetime.datetime(2026, 4, 22),
                entry_id="http://arxiv.org/abs/2604.00001v1",
            ),
        ]
        _patch_arxiv(monkeypatch, {"NLP": results})
        from nlp_arxiv_daily import storage

        monkeypatch.setattr(storage, "_current_yymm", lambda: "2604")

        # Two-step: fetch, then render — both off the same workspace
        cli.main(["--config_path", workspace["config"], "fetch"])
        # After fetch, JSON exists but markdown shouldn't yet
        assert workspace["main_json"].exists()
        assert not workspace["readme"].exists()
        assert not workspace["index"].exists()

        cli.main(["--config_path", workspace["config"], "render"])
        # Render alone produces both markdowns
        assert workspace["readme"].exists()
        assert workspace["index"].exists()
        assert "Paper A" in workspace["readme"].read_text()
