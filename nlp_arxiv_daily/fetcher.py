from __future__ import annotations

import datetime
import logging
import re
from collections.abc import Iterable

import arxiv
import requests

from nlp_arxiv_daily.types import Paper


HF_PAPERS_API = "https://huggingface.co/api/papers/"
REQUEST_TIMEOUT = 10
GITHUB_URL_RE = re.compile(r"https?://github\.com/[\w.-]+/[\w.-]+")
# arxiv API publishes a 3s minimum between requests; keep this for backfill
# loops that fire many keyword × month queries back-to-back.
BACKFILL_RATE_LIMIT_SECONDS = 3
# Default upper bound per (keyword, month) backfill query — busy keywords
# can return hundreds of arxiv submissions in a single month.
BACKFILL_DEFAULT_MAX_RESULTS = 2000


def get_authors(authors: Iterable, first_author: bool = False) -> str:
    if first_author:
        return list(authors)[0]
    return ", ".join(str(author) for author in authors)


def find_code_link(arxiv_id: str, summary: str | None = None) -> str | None:
    """
    Best-effort code repo URL lookup. Returns None when nothing is found.
    Order: HuggingFace Papers `githubRepo` → github.com URL in arxiv summary.
    """
    try:
        r = requests.get(f"{HF_PAPERS_API}{arxiv_id}", timeout=REQUEST_TIMEOUT)
        if r.status_code == 200:
            repo = r.json().get("githubRepo")
            if repo:
                return repo
    except requests.RequestException as e:
        logging.warning(f"HF Papers lookup failed for {arxiv_id}: {e}")

    if summary:
        m = GITHUB_URL_RE.search(summary)
        if m:
            return m.group(0).rstrip(".,);")

    return None


def _strip_version_suffix(short_id: str) -> str:
    """e.g. '2108.09112v1' -> '2108.09112'."""
    ver_pos = short_id.find("v")
    return short_id if ver_pos == -1 else short_id[:ver_pos]


def _result_to_paper(result) -> Paper:
    short_id = result.get_short_id()
    paper_id = _strip_version_suffix(short_id)
    first_author = get_authors(result.authors, first_author=True)
    update_time = result.updated.date()

    logging.info(f"Time = {update_time} title = {result.title} author = {first_author}")

    return Paper(
        paper_id=paper_id,
        title=result.title,
        first_author=first_author,
        update_time=update_time,
        paper_url=result.entry_id,
        code_link=find_code_link(paper_id, summary=result.summary),
        arxiv_short_id=short_id,
    )


def fetch_papers(query: str, max_results: int) -> list[Paper]:
    """
    Hit arxiv with `query`, sorted by submission date desc, and look up code
    links via HF Papers / arxiv summary fallback. No markdown rendering.
    """
    client = arxiv.Client()
    search = arxiv.Search(query=query, max_results=max_results, sort_by=arxiv.SortCriterion.SubmittedDate)
    return [_result_to_paper(r) for r in client.results(search)]


def _format_arxiv_datetime(dt: datetime.date, *, end_of_day: bool) -> str:
    """arxiv submittedDate uses YYYYMMDDHHMM. End-of-day = 23:59 to include the
    full day; otherwise 00:00 (start)."""
    suffix = "2359" if end_of_day else "0000"
    return f"{dt.year:04d}{dt.month:02d}{dt.day:02d}{suffix}"


def fetch_papers_in_range(
    query: str,
    start: datetime.date,
    end: datetime.date,
    max_results: int = BACKFILL_DEFAULT_MAX_RESULTS,
) -> list[Paper]:
    """
    Same as `fetch_papers`, but constrained to arxiv submissions in
    [start 00:00, end 23:59]. Used by the backfill subcommand. Constructs an
    arxiv.Client with the published 3s rate-limit baked in so a backfill loop
    can fire many (keyword × month) queries back-to-back without throttling.
    """
    range_clause = (
        f"submittedDate:[{_format_arxiv_datetime(start, end_of_day=False)}"
        f" TO {_format_arxiv_datetime(end, end_of_day=True)}]"
    )
    composite = f"({query}) AND {range_clause}"

    client = arxiv.Client(delay_seconds=BACKFILL_RATE_LIMIT_SECONDS)
    search = arxiv.Search(query=composite, max_results=max_results, sort_by=arxiv.SortCriterion.SubmittedDate)
    return [_result_to_paper(r) for r in client.results(search)]
