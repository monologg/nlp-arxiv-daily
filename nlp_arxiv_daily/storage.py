from __future__ import annotations

import datetime
import json
import os
import re
from collections.abc import Mapping

from nlp_arxiv_daily.records import code_link_from_value
from nlp_arxiv_daily.types import PapersByKeyword, PapersByMonth


ARXIV_KEY_RE = re.compile(r"^(\d{4})\.\d{4,5}")


def bucket_by_month(papers_by_keyword: PapersByKeyword) -> PapersByMonth:
    """
    {keyword: {paper_key: line}} → {yymm: {keyword: {paper_key: line}}}.
    paper_key matching ARXIV_KEY_RE (e.g. "2604.21637") is bucketed by its YYMM
    prefix. Keys that don't match are silently dropped — defensive against any
    legacy entries that don't follow arxiv's id format.
    """
    by_month: PapersByMonth = {}
    for keyword, papers in papers_by_keyword.items():
        for key, line in papers.items():
            m = ARXIV_KEY_RE.match(key)
            if not m:
                continue
            yymm = m.group(1)
            by_month.setdefault(yymm, {}).setdefault(keyword, {})[key] = line
    return by_month


def _yymm_to_archive_basename(yymm: str) -> str:
    return f"20{yymm[:2]}-{yymm[2:]}"


def _current_yymm() -> str:
    today = datetime.date.today()
    return f"{today.year % 100:02d}{today.month:02d}"


def _load_papers_json(path: str, into: dict) -> None:
    if not os.path.exists(path):
        return
    with open(path) as f:
        content = f.read()
    if not content:
        return
    for kw, papers in json.loads(content).items():
        into.setdefault(kw, {}).update(papers)


def load_known_code_links(main_json_path: str, archive_dir: str) -> dict[str, str | None]:
    """{paper_id: code_link_or_None} for every paper already persisted (main +
    archive). The fetcher skips the HuggingFace Papers lookup for these ids —
    with a multi-day fetch window most results are re-sightings, and one HF
    call per result was the dominant cost of a run."""
    accumulated: PapersByKeyword = {}
    _load_papers_json(main_json_path, accumulated)
    if os.path.isdir(archive_dir):
        for name in sorted(os.listdir(archive_dir)):
            if name.endswith(".json"):
                _load_papers_json(os.path.join(archive_dir, name), accumulated)
    known: dict[str, str | None] = {}
    for papers in accumulated.values():
        for paper_id, value in papers.items():
            link = code_link_from_value(value)
            # A link seen under any keyword wins over None from another.
            if paper_id not in known or link:
                known[paper_id] = link
    return known


def fill_code_links(main_json_path: str, archive_dir: str, links: Mapping[str, str]) -> int:
    """Write `links` ({paper_id: url}) into every stored record that is still
    missing a code link. Returns the number of rows updated.

    A HuggingFace lookup that fails mid-run is persisted as `code: null`,
    which reads exactly like "no repo exists" — and since the id then counts
    as known, `load_known_code_links` stops any later fetch from re-asking.
    This is the way back: look the ids up again, then fill them in here.

    Only falsy `code` fields are touched, so a link already stored (possibly a
    better one, from the arxiv summary fallback) always wins. Legacy string
    rows are skipped — their link lives inside the markdown, and rewriting
    that is not worth it for the handful of rows involved.
    """
    if not links:
        return 0
    paths = [main_json_path]
    if os.path.isdir(archive_dir):
        paths += [os.path.join(archive_dir, n) for n in sorted(os.listdir(archive_dir)) if n.endswith(".json")]

    updated = 0
    for path in paths:
        if not os.path.exists(path):
            continue
        with open(path) as f:
            content = f.read()
        if not content:
            continue
        bucket = json.loads(content)
        touched = 0
        for papers in bucket.values():
            for paper_id, link in links.items():
                value = papers.get(paper_id)
                if isinstance(value, dict) and not value.get("code"):
                    value["code"] = link
                    touched += 1
        # Leave the file (and its mtime) alone when nothing matched.
        if touched:
            with open(path, "w") as f:
                json.dump(bucket, f)
            updated += touched
    return updated


def _ordered_bucket(bucket: PapersByKeyword, keyword_order: list[str] | None) -> PapersByKeyword:
    """Return `bucket` with keys reordered per `keyword_order`. Keys not in the
    order list keep their original relative position at the end. `None` is identity."""
    if not keyword_order:
        return bucket
    ordered: PapersByKeyword = {k: bucket[k] for k in keyword_order if k in bucket}
    for k, v in bucket.items():
        if k not in ordered:
            ordered[k] = v
    return ordered


def write_papers_split(
    new_papers_list: list[PapersByKeyword],
    main_json_path: str,
    archive_dir: str,
    current_yymm: str | None = None,
    keyword_order: list[str] | None = None,
) -> None:
    """
    Re-bucket all known papers (existing main + archive + new daily) by YYMM and
    write current month → main_json_path, older months → archive_dir/YYYY-MM.json.

    Idempotent: running with new_papers_list=[] re-distributes existing data.
    Migration is implicit — first run with a legacy "all months in main" file
    splits it.

    `keyword_order` (when given) controls the order of top-level keyword keys
    in every emitted JSON file. The Astro site iterates JSON entries in
    insertion order, so this makes config.yaml the source of truth for both
    markdown and the gitpage site. Keys missing from the order list are
    appended at the end.
    """
    if current_yymm is None:
        current_yymm = _current_yymm()

    accumulated: PapersByKeyword = {}
    _load_papers_json(main_json_path, accumulated)
    if os.path.isdir(archive_dir):
        for name in sorted(os.listdir(archive_dir)):
            if name.endswith(".json"):
                _load_papers_json(os.path.join(archive_dir, name), accumulated)

    for new_papers in new_papers_list:
        for kw, papers in new_papers.items():
            accumulated.setdefault(kw, {}).update(papers)

    by_month = bucket_by_month(accumulated)

    main_dir = os.path.dirname(main_json_path)
    if main_dir:
        os.makedirs(main_dir, exist_ok=True)
    main_bucket = _ordered_bucket(by_month.pop(current_yymm, {}), keyword_order)
    with open(main_json_path, "w") as f:
        json.dump(main_bucket, f)

    os.makedirs(archive_dir, exist_ok=True)
    for yymm, bucket in by_month.items():
        archive_path = os.path.join(archive_dir, f"{_yymm_to_archive_basename(yymm)}.json")
        with open(archive_path, "w") as f:
            json.dump(_ordered_bucket(bucket, keyword_order), f)


def update_json_file(filename, data_dict):
    """
    daily update json file using data_dict
    """
    if os.path.exists(filename):
        with open(filename) as f:
            content = f.read()
        m = json.loads(content) if content else {}
    else:
        m = {}

    json_data = m.copy()

    # update papers in each keywords
    for data in data_dict:
        for keyword in data:
            papers = data[keyword]

            if keyword in json_data:
                json_data[keyword].update(papers)
            else:
                json_data[keyword] = papers

    with open(filename, "w") as f:
        json.dump(json_data, f)
