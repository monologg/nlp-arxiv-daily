from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import TypedDict


@dataclass(frozen=True)
class Paper:
    paper_id: str
    title: str
    first_author: str
    update_time: date
    paper_url: str
    code_link: str | None


class KeywordConfig(TypedDict):
    filters: list[str]


PapersByKeyword = dict[str, dict[str, str]]
PapersByMonth = dict[str, dict[str, dict[str, str]]]
