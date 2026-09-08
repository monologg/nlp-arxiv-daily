"""Conversions between `Paper`, the structured `WebRecord` persisted in the
gitpage JSON files, and the legacy one-line markdown row.

The JSON files under docs/ are append-only across years, so both shapes
coexist indefinitely: rows written before the switch stay strings, anything
the pipeline fetches afterwards is a dict. `web_record_to_line` lets the
(retired, but still tested) markdown renderer treat both uniformly.
"""

from __future__ import annotations

import re

from nlp_arxiv_daily.types import Paper, PaperValue, WebRecord


# Legacy rows carry the code link as `**[<text>](<url>)**` — bullet rows as
# `Code: **[url](url)**`, README pipe rows as `|**[link](url)**|`.
_LEGACY_CODE_RE = re.compile(r"\*\*\[[^\]]*\]\((https?://[^)]+)\)\*\*")


def paper_to_web_record(p: Paper) -> WebRecord:
    authors = list(p.authors) if p.authors else [p.first_author]
    return {
        "date": p.update_time.isoformat(),
        "title": p.title,
        "authors": authors,
        "url": p.paper_url,
        "code": p.code_link,
        "abstract": p.abstract,
        "categories": list(p.categories),
    }


def web_line(date: str, title: str, first_author: str, url: str, code: str | None) -> str:
    """The legacy gitpage row: `- <date>, **<title>**, <author> et.al., Paper: [url](url)[, Code: **[c](c)**]`."""
    line = f"- {date}, **{title}**, {first_author} et.al., Paper: [{url}]({url})"
    if code:
        line += f", Code: **[{code}]({code})**"
    return line + "\n"


def web_record_to_line(value: PaperValue) -> str:
    """Legacy string rows pass through untouched; dict records are rendered
    into the identical line shape."""
    if isinstance(value, str):
        return value
    authors = value.get("authors") or [""]
    return web_line(value["date"], value["title"], authors[0], value["url"], value.get("code"))


def code_link_from_value(value: PaperValue) -> str | None:
    """Code link already stored for a paper, from either value shape. Lets a
    re-fetch reuse it instead of asking HuggingFace Papers again."""
    if isinstance(value, dict):
        return value.get("code") or None
    m = _LEGACY_CODE_RE.search(value)
    return m.group(1) if m else None
