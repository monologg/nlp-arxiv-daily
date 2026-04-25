from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import TypedDict


@dataclass(frozen=True)
class Paper:
    paper_id: str  # versionless arxiv id, e.g. "2108.09112"
    title: str
    first_author: str
    update_time: date
    paper_url: str
    code_link: str | None
    arxiv_short_id: str = ""  # raw arxiv short id incl. version, e.g. "2108.09112v1"


class KeywordConfig(TypedDict):
    filters: list[str]


PapersByKeyword = dict[str, dict[str, str]]
PapersByMonth = dict[str, dict[str, dict[str, str]]]
