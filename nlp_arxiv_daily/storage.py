from __future__ import annotations

import datetime
import json
import os
import re

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


def write_papers_split(
    new_papers_list: list[PapersByKeyword],
    main_json_path: str,
    archive_dir: str,
    current_yymm: str | None = None,
) -> None:
    """
    Re-bucket all known papers (existing main + archive + new daily) by YYMM and
    write current month → main_json_path, older months → archive_dir/YYYY-MM.json.

    Idempotent: running with new_papers_list=[] re-distributes existing data.
    Migration is implicit — first run with a legacy "all months in main" file
    splits it.
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
    main_bucket = by_month.pop(current_yymm, {})
    with open(main_json_path, "w") as f:
        json.dump(main_bucket, f)

    os.makedirs(archive_dir, exist_ok=True)
    for yymm, bucket in by_month.items():
        archive_path = os.path.join(archive_dir, f"{_yymm_to_archive_basename(yymm)}.json")
        with open(archive_path, "w") as f:
            json.dump(bucket, f)


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
