from __future__ import annotations

import datetime
import logging
import re
import time
from collections.abc import Iterable

import arxiv
import requests
from tenacity import (
    retry,
    retry_if_exception,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
    wait_random,
)

from nlp_arxiv_daily.types import Paper


HF_PAPERS_API = "https://huggingface.co/api/papers/"
REQUEST_TIMEOUT = 10
GITHUB_URL_RE = re.compile(r"https?://github\.com/[\w.-]+/[\w.-]+")

# arxiv API publishes a 3s minimum between requests, but multi-keyword
# back-to-back fetches and bulk backfill pagination both trigger 429s in
# practice — and GH Actions IPs get throttled harder than typical clients,
# so we go well above the published minimum.
DAILY_RATE_LIMIT_SECONDS = 15
BACKFILL_RATE_LIMIT_SECONDS = 5
# arxiv.Client default is 3 in-library retries (fixed interval); bump it
# before our outer tenacity retry kicks in.
DAILY_NUM_RETRIES = 10
BACKFILL_NUM_RETRIES = 10
# config caps display at max_results=10 per keyword, so a library-default
# page_size=100 just inflates response payloads without giving us anything.
# Smaller pages also reduce the chance of tripping arxiv's per-IP throttle.
DAILY_PAGE_SIZE = 20
# Default upper bound per (keyword, month) backfill query — busy keywords
# can return hundreds of arxiv submissions in a single month.
BACKFILL_DEFAULT_MAX_RESULTS = 2000

# HuggingFace Papers gets one lookup per arxiv result. Without throttle, a
# 100-paper page fires ~10 req/s. 0.5s gap = 2 req/s, polite and still fast
# enough that a daily run finishes in seconds.
HF_MIN_INTERVAL_SECONDS = 0.5
_hf_last_call_ts: float = 0.0

# Module-level singleton so every keyword in cmd_fetch shares the same
# client, and the arxiv library's per-client rate limiter governs *across*
# keyword boundaries (not just within a single fetch_papers call).
_DAILY_CLIENT: arxiv.Client | None = None


def _get_daily_client() -> arxiv.Client:
    global _DAILY_CLIENT
    if _DAILY_CLIENT is None:
        _DAILY_CLIENT = arxiv.Client(
            page_size=DAILY_PAGE_SIZE,
            delay_seconds=DAILY_RATE_LIMIT_SECONDS,
            num_retries=DAILY_NUM_RETRIES,
        )
    return _DAILY_CLIENT


def get_authors(authors: Iterable, first_author: bool = False) -> str:
    if first_author:
        return list(authors)[0]
    return ", ".join(str(author) for author in authors)


def _is_retryable_hf_error(exc: BaseException) -> bool:
    """Retry HF Papers calls only on 429/5xx and connection-level failures."""
    if isinstance(exc, requests.HTTPError):
        resp = getattr(exc, "response", None)
        status = getattr(resp, "status_code", None)
        return status == 429 or (status is not None and 500 <= status < 600)
    return isinstance(exc, requests.ConnectionError | requests.Timeout)


@retry(
    retry=retry_if_exception(_is_retryable_hf_error),
    wait=wait_exponential(multiplier=2, min=2, max=30) + wait_random(0, 2),
    stop=stop_after_attempt(3),
    reraise=True,
)
def _hf_lookup(arxiv_id: str) -> dict | None:
    """Hit HF Papers API once with module-level throttle. Returns parsed
    JSON dict on 200, None on 404. Raises on retryable errors so the
    tenacity decorator can back off; non-retryable HTTP errors surface.
    """
    global _hf_last_call_ts
    elapsed = time.monotonic() - _hf_last_call_ts
    if elapsed < HF_MIN_INTERVAL_SECONDS:
        time.sleep(HF_MIN_INTERVAL_SECONDS - elapsed)
    _hf_last_call_ts = time.monotonic()

    r = requests.get(f"{HF_PAPERS_API}{arxiv_id}", timeout=REQUEST_TIMEOUT)
    if r.status_code == 404:
        return None
    r.raise_for_status()
    return r.json()


def find_code_link(arxiv_id: str, summary: str | None = None) -> str | None:
    """
    Best-effort code repo URL lookup. Returns None when nothing is found.
    Order: HuggingFace Papers `githubRepo` → github.com URL in arxiv summary.

    Failure here is non-fatal: a flaky HF Papers API should not kill the
    whole daily run, so retry-exhausted errors are swallowed and the
    summary fallback still gets a chance.
    """
    try:
        payload = _hf_lookup(arxiv_id)
        if payload:
            repo = payload.get("githubRepo")
            if repo:
                return repo
    except (requests.RequestException, requests.HTTPError) as e:
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
    """Convert an arxiv.Result to our Paper dataclass.

    Uses `result.published.date()` (submission date), NOT
    `result.updated.date()` (latest revision). Backfilled papers can have
    revisions long after submission — the revision date scrambles them
    across the wrong months in the archive UI (e.g. an Aug-2025 submission
    revised in Jan 2026 was showing up dated 2026-01 inside /archive/2025-08/).
    The arxiv id (`2508.xxxxx`) already encodes the submission month and
    that's what we bucket by; the display date should match.
    """
    short_id = result.get_short_id()
    paper_id = _strip_version_suffix(short_id)
    first_author = get_authors(result.authors, first_author=True)
    update_time = result.published.date()

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


@retry(
    retry=retry_if_exception_type(arxiv.HTTPError),
    wait=wait_exponential(multiplier=10, min=10, max=120) + wait_random(0, 5),
    stop=stop_after_attempt(4),
    reraise=True,
)
def fetch_papers(query: str, max_results: int) -> list[Paper]:
    """
    Hit arxiv with `query`, sorted by submission date desc, and look up code
    links via HF Papers / arxiv summary fallback. No markdown rendering.

    Wrapped in tenacity outer retry so a 429 storm that exhausts the
    arxiv library's in-client retries (10 × 5s) gets another 4 attempts
    with exponential backoff (~10s → 80s + jitter) before giving up.
    """
    client = _get_daily_client()
    search = arxiv.Search(query=query, max_results=max_results, sort_by=arxiv.SortCriterion.SubmittedDate)
    return [_result_to_paper(r) for r in client.results(search)]


def _format_arxiv_datetime(dt: datetime.date, *, end_of_day: bool) -> str:
    """arxiv submittedDate uses YYYYMMDDHHMM. End-of-day = 23:59 to include the
    full day; otherwise 00:00 (start)."""
    suffix = "2359" if end_of_day else "0000"
    return f"{dt.year:04d}{dt.month:02d}{dt.day:02d}{suffix}"


@retry(
    retry=retry_if_exception_type(arxiv.HTTPError),
    wait=wait_exponential(multiplier=10, min=10, max=120) + wait_random(0, 5),
    stop=stop_after_attempt(4),
    reraise=True,
)
def fetch_papers_in_range(
    query: str,
    start: datetime.date,
    end: datetime.date,
    max_results: int = BACKFILL_DEFAULT_MAX_RESULTS,
    delay_seconds: int = BACKFILL_RATE_LIMIT_SECONDS,
) -> list[Paper]:
    """
    Same as `fetch_papers`, but constrained to arxiv submissions in
    [start 00:00, end 23:59]. Used by the backfill subcommand. Constructs an
    arxiv.Client with the published 3s rate-limit baked in so a backfill loop
    can fire many (keyword × month) queries back-to-back without throttling.

    `delay_seconds` overrides the default per-request gap — bump it when
    running large multi-keyword backfills that have been seeing 429s.
    """
    range_clause = (
        f"submittedDate:[{_format_arxiv_datetime(start, end_of_day=False)}"
        f" TO {_format_arxiv_datetime(end, end_of_day=True)}]"
    )
    composite = f"({query}) AND {range_clause}"

    client = arxiv.Client(
        delay_seconds=delay_seconds,
        num_retries=BACKFILL_NUM_RETRIES,
    )
    search = arxiv.Search(query=composite, max_results=max_results, sort_by=arxiv.SortCriterion.SubmittedDate)
    return [_result_to_paper(r) for r in client.results(search)]
