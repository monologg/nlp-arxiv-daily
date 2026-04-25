from __future__ import annotations

import logging
import re
from collections.abc import Iterable

import arxiv
import requests

from nlp_arxiv_daily.types import Paper


HF_PAPERS_API = "https://huggingface.co/api/papers/"
REQUEST_TIMEOUT = 10
GITHUB_URL_RE = re.compile(r"https?://github\.com/[\w.-]+/[\w.-]+")


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


def fetch_papers(query: str, max_results: int) -> list[Paper]:
    """
    Hit arxiv with `query`, sorted by submission date desc, and look up code
    links via HF Papers / arxiv summary fallback. No markdown rendering.
    """
    client = arxiv.Client()
    search = arxiv.Search(query=query, max_results=max_results, sort_by=arxiv.SortCriterion.SubmittedDate)

    papers: list[Paper] = []
    for result in client.results(search):
        short_id = result.get_short_id()
        paper_id = _strip_version_suffix(short_id)
        first_author = get_authors(result.authors, first_author=True)
        update_time = result.updated.date()

        logging.info(f"Time = {update_time} title = {result.title} author = {first_author}")

        papers.append(
            Paper(
                paper_id=paper_id,
                title=result.title,
                first_author=first_author,
                update_time=update_time,
                paper_url=result.entry_id,
                code_link=find_code_link(paper_id, summary=result.summary),
                arxiv_short_id=short_id,
            )
        )

    return papers
