from __future__ import annotations

import datetime
import json
import logging
import os
import re

import yaml

from nlp_arxiv_daily.fetcher import fetch_papers
from nlp_arxiv_daily.types import PapersByKeyword, PapersByMonth


logging.basicConfig(format="[%(asctime)s %(levelname)s] %(message)s", datefmt="%m/%d/%Y %H:%M:%S", level=logging.INFO)

ARXIV_KEY_RE = re.compile(r"^(\d{4})\.\d{4,5}")


def load_config(config_file: str) -> dict:
    """
    config_file: input config file path
    return: a dict of configuration
    """

    # make filters pretty
    def pretty_filters(**config) -> dict:
        keywords = {}
        EXCAPE = '"'
        QUOTA = ""  # NO-USE
        OR = "OR"  # TODO

        def parse_filters(filters: list):
            ret = ""
            for idx in range(0, len(filters)):
                filter = filters[idx]
                if len(filter.split()) > 1:
                    ret += EXCAPE + filter + EXCAPE
                else:
                    ret += QUOTA + filter + QUOTA
                if idx != len(filters) - 1:
                    ret += OR
            return ret

        for k, v in config["keywords"].items():
            keywords[k] = parse_filters(v["filters"])
        return keywords

    with open(config_file, "r") as f:
        config = yaml.load(f, Loader=yaml.FullLoader)
        config["kv"] = pretty_filters(**config)
        logging.info(f"config = {config}")
    return config


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


def sort_papers(papers):
    output = {}
    keys = list(papers.keys())
    keys.sort(reverse=True)
    for key in keys:
        output[key] = papers[key]
    return output


def get_daily_papers(topic, query="nlp", max_results=2):
    """
    Backward-compat adapter: fetch via `fetcher.fetch_papers`, then pre-render
    markdown rows in the legacy shape. The pre-rendering lives here only until
    PRSL-66 splits a proper renderer module out.
    """
    papers = fetch_papers(query=query, max_results=max_results)

    content: dict[str, str] = {}
    content_to_web: dict[str, str] = {}
    for p in papers:
        code_md = f"**[link]({p.code_link})**" if p.code_link else "null"
        content[p.paper_id] = "|**{}**|**{}**|{} et.al.|[{}]({})|{}|\n".format(
            p.update_time, p.title, p.first_author, p.arxiv_short_id, p.paper_url, code_md
        )
        web_line = "- {}, **{}**, {} et.al., Paper: [{}]({})".format(
            p.update_time, p.title, p.first_author, p.paper_url, p.paper_url
        )
        if p.code_link:
            web_line += f", Code: **[{p.code_link}]({p.code_link})**"
        content_to_web[p.paper_id] = web_line + "\n"

    return {topic: content}, {topic: content_to_web}


def _yymm_to_archive_basename(yymm: str) -> str:
    return f"20{yymm[:2]}-{yymm[2:]}"


def _current_yymm() -> str:
    today = datetime.date.today()
    return f"{today.year % 100:02d}{today.month:02d}"


def _load_papers_json(path: str, into: dict) -> None:
    if not os.path.exists(path):
        return
    with open(path, "r") as f:
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
        with open(filename, "r") as f:
            content = f.read()
        m = json.loads(content) if content else {}
    else:
        m = {}

    json_data = m.copy()

    # update papers in each keywords
    for data in data_dict:
        for keyword in data.keys():
            papers = data[keyword]

            if keyword in json_data.keys():
                json_data[keyword].update(papers)
            else:
                json_data[keyword] = papers

    with open(filename, "w") as f:
        json.dump(json_data, f)


def json_to_md(
    filename,
    md_filename,
    task="",
    to_web=False,
    use_title=True,
    use_tc=True,
    show_badge=True,
    user_name="",
    repo_name="",
    archive_index_link="",
):
    """
    @param filename: str
    @param md_filename: str
    @return None
    """

    def pretty_math(s: str) -> str:
        ret = ""
        match = re.search(r"\$.*\$", s)
        if match is None:
            return s
        math_start, math_end = match.span()
        space_trail = space_leading = ""
        if s[:math_start][-1] != " " and "*" != s[:math_start][-1]:
            space_trail = " "
        if s[math_end:][0] != " " and "*" != s[math_end:][0]:
            space_leading = " "
        ret += s[:math_start]
        ret += f"{space_trail}${match.group()[1:-1].strip()}${space_leading}"
        ret += s[math_end:]
        return ret

    DateNow = datetime.date.today()
    DateNow = str(DateNow)
    DateNow = DateNow.replace("-", ".")

    with open(filename, "r") as f:
        content = f.read()
    data = json.loads(content) if content else {}

    repo_slug = f"{user_name}/{repo_name}"
    with open(md_filename, "w") as f:
        if (use_title is True) and (to_web is True):
            f.write("---\n" + "layout: default\n" + "---\n\n")

        if show_badge is True:
            f.write("[![Contributors][contributors-shield]][contributors-url]\n")
            f.write("[![Forks][forks-shield]][forks-url]\n")
            f.write("[![Stargazers][stars-shield]][stars-url]\n")
            f.write("[![Issues][issues-shield]][issues-url]\n\n")

        if use_title is True:
            f.write("## Updated on " + DateNow + "\n\n")
        else:
            f.write("> Updated on " + DateNow + "\n\n")

        if archive_index_link:
            f.write(f"> Older months: [archive]({archive_index_link})\n\n")

        # Add: table of contents
        if use_tc is True:
            f.write("<details>\n")
            f.write("  <summary>Table of Contents</summary>\n")
            f.write("  <ol>\n")
            for keyword in data.keys():
                day_content = data[keyword]
                if not day_content:
                    continue
                kw = keyword.replace(" ", "-")
                f.write(f"    <li><a href='#{kw.lower()}'>{keyword}</a></li>\n")
            f.write("  </ol>\n")
            f.write("</details>\n\n")

        for keyword in data.keys():
            day_content = data[keyword]
            if not day_content:
                continue
            # the head of each part
            f.write(f"## {keyword}\n\n")

            if use_title is True and to_web is False:
                f.write("|Publish Date|Title|Authors|PDF|Code|\n" + "|---|---|---|---|---|\n")

            # sort papers by date
            day_content = sort_papers(day_content)

            for _, v in day_content.items():
                if v is not None:
                    f.write(pretty_math(v))  # make latex pretty

            f.write("\n")

            # Add: back to top
            top_info = f"#Updated on {DateNow}"
            top_info = top_info.replace(" ", "-").replace(".", "")
            f.write(f"<p align=right>(<a href='{top_info.lower()}'>back to top</a>)</p>\n\n")

        if show_badge is True:
            f.write(
                f"[contributors-shield]: https://img.shields.io/github/contributors/{repo_slug}.svg?style=for-the-badge\n"
            )
            f.write(f"[contributors-url]: https://github.com/{repo_slug}/graphs/contributors\n")
            f.write(f"[forks-shield]: https://img.shields.io/github/forks/{repo_slug}.svg?style=for-the-badge\n")
            f.write(f"[forks-url]: https://github.com/{repo_slug}/network/members\n")
            f.write(f"[stars-shield]: https://img.shields.io/github/stars/{repo_slug}.svg?style=for-the-badge\n")
            f.write(f"[stars-url]: https://github.com/{repo_slug}/stargazers\n")
            f.write(f"[issues-shield]: https://img.shields.io/github/issues/{repo_slug}.svg?style=for-the-badge\n")
            f.write(f"[issues-url]: https://github.com/{repo_slug}/issues\n\n")

    logging.info(f"{task} finished")


def render_archive_pages(
    archive_json_dir: str,
    archive_md_dir: str,
    to_web: bool = False,
    show_badge: bool = False,
    user_name: str = "",
    repo_name: str = "",
) -> None:
    """
    Render every {YYYY-MM}.json under archive_json_dir to a sibling
    {YYYY-MM}.md under archive_md_dir, plus an index.md listing months desc.
    No-op when archive_json_dir doesn't exist.
    """
    if not os.path.isdir(archive_json_dir):
        return
    os.makedirs(archive_md_dir, exist_ok=True)

    months = []
    for name in sorted(os.listdir(archive_json_dir)):
        if not name.endswith(".json"):
            continue
        stem = name[:-5]
        json_to_md(
            os.path.join(archive_json_dir, name),
            os.path.join(archive_md_dir, f"{stem}.md"),
            task=f"archive {stem}",
            to_web=to_web,
            show_badge=show_badge,
            user_name=user_name,
            repo_name=repo_name,
        )
        months.append(stem)

    _write_archive_index(archive_md_dir, months, to_web=to_web)


def _write_archive_index(archive_md_dir: str, months: list, to_web: bool = False) -> None:
    path = os.path.join(archive_md_dir, "index.md")
    months_desc = sorted(months, reverse=True)
    with open(path, "w") as f:
        if to_web:
            f.write("---\nlayout: default\n---\n\n")
        f.write("# Archive\n\n")
        f.write("Older monthly snapshots.\n\n")
        f.write("| Month |\n|---|\n")
        for m in months_desc:
            f.write(f"| [{m}]({m}.md) |\n")


def demo(**config):
    data_collector = []
    data_collector_web = []

    keywords = config["kv"]
    max_results = config["max_results"]
    publish_readme = config["publish_readme"]
    publish_gitpage = config["publish_gitpage"]
    show_badge = config["show_badge"]
    user_name = config["user_name"]
    repo_name = config["repo_name"]

    logging.info("GET daily papers begin")
    for topic, keyword in keywords.items():
        logging.info(f"Keyword: {topic}")
        data, data_web = get_daily_papers(topic, query=keyword, max_results=max_results)
        data_collector.append(data)
        data_collector_web.append(data_web)
        print("\n")
    logging.info("GET daily papers end")

    # 1. update README.md file (current month only; older months → docs/archive/)
    if publish_readme:
        json_file = config["json_readme_path"]
        md_file = config["md_readme_path"]
        archive_json_dir = config["archive_readme_json_dir"]
        archive_md_dir = config["archive_readme_md_dir"]
        write_papers_split(data_collector, json_file, archive_json_dir)
        json_to_md(
            json_file,
            md_file,
            task="Update Readme",
            show_badge=show_badge,
            user_name=user_name,
            repo_name=repo_name,
            archive_index_link="docs/archive/index.md",
        )
        render_archive_pages(
            archive_json_dir,
            archive_md_dir,
            show_badge=show_badge,
            user_name=user_name,
            repo_name=repo_name,
        )

    # 2. update docs/index.md file (to gitpage)
    if publish_gitpage:
        json_file = config["json_gitpage_path"]
        md_file = config["md_gitpage_path"]
        archive_json_dir = config["archive_gitpage_json_dir"]
        archive_md_dir = config["archive_gitpage_md_dir"]
        write_papers_split(data_collector_web, json_file, archive_json_dir)
        json_to_md(
            json_file,
            md_file,
            task="Update GitPage",
            to_web=True,
            show_badge=show_badge,
            user_name=user_name,
            repo_name=repo_name,
            archive_index_link="archive-web/index.md",
        )
        render_archive_pages(
            archive_json_dir,
            archive_md_dir,
            to_web=True,
            show_badge=show_badge,
            user_name=user_name,
            repo_name=repo_name,
        )
