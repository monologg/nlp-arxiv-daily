"""Contract smoke tests against the real arXiv and HuggingFace Papers APIs.

Deselected by default (see `addopts` in pyproject.toml); run them with
`make test-integration`. Two tests, one arXiv request each:

- `test_arxiv_search_smoke` sends a plain `arxiv.Search` and checks that a
  Result still exposes the fields the fetcher reads.
- `test_daily_fetch_end_to_end` goes through the same path as the daily cron
  (`cmd_fetch` -> `fetch_recent_papers` -> date-window query), with a
  one-keyword config and a two-result cap, so it adds at most a couple of
  HuggingFace lookups.
"""

import json
import textwrap
import time
from pathlib import Path

import arxiv
import pytest

from nlp_arxiv_daily.cli import cmd_fetch
from nlp_arxiv_daily.core import load_config
from nlp_arxiv_daily.types import WebRecord


pytestmark = pytest.mark.integration

# The two tests use separate arxiv.Client instances, whose rate limiters do not
# know about each other; wait out arXiv's published 3s minimum between them.
ARXIV_REQUEST_GAP_SECONDS = 3


def test_arxiv_search_smoke():
    """The arXiv API answers, and each Result exposes the fields
    `fetcher._result_to_paper` reads."""
    client = arxiv.Client()
    search = arxiv.Search(
        query="NLP",
        max_results=2,
        sort_by=arxiv.SortCriterion.SubmittedDate,
    )
    results = list(client.results(search))

    assert len(results) > 0, "arxiv returned no results for query='NLP'"

    for r in results:
        assert r.get_short_id()
        assert r.title
        assert r.entry_id
        assert r.authors and len(r.authors) > 0
        assert r.published is not None
        assert r.summary
        assert r.categories

    time.sleep(ARXIV_REQUEST_GAP_SECONDS)


def _write_config(tmp_path: Path) -> Path:
    docs = tmp_path / "docs"
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        textwrap.dedent(
            f"""
            user_name: "user"
            repo_name: "repo"
            show_authors: true
            show_links: true
            show_badge: false
            daily_lookback_days: 7
            max_results: 2
            publish_readme: false
            publish_gitpage: true
            json_gitpage_path: "{docs / "nlp-arxiv-daily-web.json"}"
            archive_gitpage_json_dir: "{docs / "archive-web"}"
            keywords:
              "NLP":
                filters: ["NLP", "Natural Language Processing"]
            """
        ).strip()
    )
    return cfg


def test_daily_fetch_end_to_end(tmp_path):
    """The cron's fetch step queries the last `daily_lookback_days` days, looks
    up code links on HuggingFace Papers, and persists structured records."""
    config = load_config(str(_write_config(tmp_path)))

    cmd_fetch(config)

    # A 7-day window can straddle a month boundary, so read the current-month
    # file and any archive month the run wrote.
    files = [Path(config["json_gitpage_path"]), *sorted(Path(config["archive_gitpage_json_dir"]).glob("*.json"))]
    records = {}
    for f in files:
        records.update(json.loads(f.read_text()).get("NLP", {}))

    assert 0 < len(records) <= config["max_results"], f"unexpected row count: {len(records)}"

    for paper_id, rec in records.items():
        assert isinstance(rec, dict), f"{paper_id}: expected a record, got {rec!r}"
        # Exactly the persisted fields: abstracts are fetched but not stored.
        assert set(rec) == set(WebRecord.__annotations__), f"{paper_id}: unexpected keys {sorted(rec)}"
        assert rec["title"] and rec["authors"] and rec["url"].startswith("http")
        assert rec["date"] and rec["categories"]
        assert rec["code"] is None or rec["code"].startswith("http")
