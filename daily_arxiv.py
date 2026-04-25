"""Backward-compat shim. Real logic lives in `nlp_arxiv_daily`.

This module exists so that:
- `python daily_arxiv.py` (the cron workflow entrypoint) keeps working.
- `from daily_arxiv import ...` (used by tests) keeps resolving the same names.
- `monkeypatch.setattr(daily_arxiv.requests, "get", ...)` keeps working,
  because `requests` is imported here.
"""

import requests  # noqa: F401  re-exported for tests that monkeypatch daily_arxiv.requests

from nlp_arxiv_daily import (
    ARXIV_KEY_RE,
    GITHUB_URL_RE,
    HF_PAPERS_API,
    REQUEST_TIMEOUT,
    bucket_by_month,
    demo,
    fetch_papers,
    find_code_link,
    get_authors,
    get_daily_papers,
    json_to_md,
    load_config,
    render_archive_pages,
    sort_papers,
    update_json_file,
    write_papers_split,
)
from nlp_arxiv_daily.__main__ import main


__all__ = [
    "ARXIV_KEY_RE",
    "GITHUB_URL_RE",
    "HF_PAPERS_API",
    "REQUEST_TIMEOUT",
    "bucket_by_month",
    "demo",
    "fetch_papers",
    "find_code_link",
    "get_authors",
    "get_daily_papers",
    "json_to_md",
    "load_config",
    "render_archive_pages",
    "sort_papers",
    "update_json_file",
    "write_papers_split",
]


if __name__ == "__main__":
    main()
