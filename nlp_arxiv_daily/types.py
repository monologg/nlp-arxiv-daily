from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, TypedDict


@dataclass(frozen=True)
class Paper:
    paper_id: str  # versionless arxiv id, e.g. "2108.09112"
    title: str
    first_author: str
    update_time: date
    paper_url: str
    code_link: str | None
    arxiv_short_id: str = ""  # raw arxiv short id incl. version, e.g. "2108.09112v1"
    # Structured extras captured since the web JSON moved to dict records.
    # Tuples (not lists) so the frozen dataclass stays hashable.
    authors: tuple[str, ...] = ()
    abstract: str = ""
    categories: tuple[str, ...] = ()  # arxiv categories, primary first


class KeywordConfig(TypedDict):
    filters: list[str]


class WebRecord(TypedDict):
    """One paper in the gitpage JSON files (docs/*.json). Replaces the
    one-line markdown string; old files still hold strings, so consumers
    must accept `str | WebRecord`."""

    date: str  # ISO YYYY-MM-DD submission date
    title: str
    authors: list[str]
    url: str  # arxiv abs URL incl. version
    code: str | None
    abstract: str
    categories: list[str]


# Value is a legacy markdown row (str) or a WebRecord (dict).
PaperValue = str | dict[str, Any]
PapersByKeyword = dict[str, dict[str, PaperValue]]
PapersByMonth = dict[str, dict[str, dict[str, PaperValue]]]
