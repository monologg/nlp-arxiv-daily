from __future__ import annotations

import datetime
import json
import logging
import os
import re

from nlp_arxiv_daily.types import PapersByKeyword


def sort_papers(papers: dict) -> dict:
    """Return papers ordered by descending key (newest paper id first)."""
    output = {}
    for key in sorted(papers.keys(), reverse=True):
        output[key] = papers[key]
    return output


def pretty_math(s: str) -> str:
    """Tighten whitespace around inline `$...$` math so markdown renders it correctly."""
    match = re.search(r"\$.*\$", s)
    if match is None:
        return s
    math_start, math_end = match.span()
    space_trail = space_leading = ""
    if s[:math_start][-1] != " " and s[:math_start][-1] != "*":
        space_trail = " "
    if s[math_end:][0] != " " and s[math_end:][0] != "*":
        space_leading = " "
    return s[:math_start] + f"{space_trail}${match.group()[1:-1].strip()}${space_leading}" + s[math_end:]


def _date_now_str(today: datetime.date) -> str:
    return today.isoformat().replace("-", ".")


def _jekyll_front_matter() -> str:
    return "---\nlayout: default\n---\n\n"


def _badge_shields() -> str:
    return (
        "[![Contributors][contributors-shield]][contributors-url]\n"
        "[![Forks][forks-shield]][forks-url]\n"
        "[![Stargazers][stars-shield]][stars-url]\n"
        "[![Issues][issues-shield]][issues-url]\n\n"
    )


def _badge_link_definitions(repo_slug: str) -> str:
    return (
        f"[contributors-shield]: https://img.shields.io/github/contributors/{repo_slug}.svg?style=for-the-badge\n"
        f"[contributors-url]: https://github.com/{repo_slug}/graphs/contributors\n"
        f"[forks-shield]: https://img.shields.io/github/forks/{repo_slug}.svg?style=for-the-badge\n"
        f"[forks-url]: https://github.com/{repo_slug}/network/members\n"
        f"[stars-shield]: https://img.shields.io/github/stars/{repo_slug}.svg?style=for-the-badge\n"
        f"[stars-url]: https://github.com/{repo_slug}/stargazers\n"
        f"[issues-shield]: https://img.shields.io/github/issues/{repo_slug}.svg?style=for-the-badge\n"
        f"[issues-url]: https://github.com/{repo_slug}/issues\n\n"
    )


def _title_line(date_now: str, use_title: bool) -> str:
    if use_title:
        return f"## Updated on {date_now}\n\n"
    return f"> Updated on {date_now}\n\n"


def _archive_link_line(archive_index_link: str) -> str:
    if not archive_index_link:
        return ""
    return f"> Older months: [archive]({archive_index_link})\n\n"


def _toc(data: PapersByKeyword) -> str:
    lines = ["<details>\n", "  <summary>Table of Contents</summary>\n", "  <ol>\n"]
    for keyword, day_content in data.items():
        if not day_content:
            continue
        kw = keyword.replace(" ", "-")
        lines.append(f"    <li><a href='#{kw.lower()}'>{keyword}</a></li>\n")
    lines.append("  </ol>\n")
    lines.append("</details>\n\n")
    return "".join(lines)


def _back_to_top_line(date_now: str) -> str:
    anchor = f"#Updated on {date_now}".replace(" ", "-").replace(".", "").lower()
    return f"<p align=right>(<a href='{anchor}'>back to top</a>)</p>\n\n"


def _keyword_section(
    keyword: str,
    day_content: dict,
    *,
    to_web: bool,
    use_title: bool,
    date_now: str,
) -> str:
    lines = [f"## {keyword}\n\n"]
    if use_title and not to_web:
        lines.append("|Publish Date|Title|Authors|PDF|Code|\n|---|---|---|---|---|\n")
    for _, v in sort_papers(day_content).items():
        if v is not None:
            lines.append(pretty_math(v))
    lines.append("\n")
    lines.append(_back_to_top_line(date_now))
    return "".join(lines)


def render_index(
    json_path: str,
    md_path: str,
    *,
    task: str = "",
    to_web: bool = False,
    use_title: bool = True,
    use_tc: bool = True,
    show_badge: bool = True,
    user_name: str = "",
    repo_name: str = "",
    archive_index_link: str = "",
    today: datetime.date | None = None,
) -> None:
    """Render a JSON of {keyword: {paper_id: row}} to a markdown index page.

    `today` is exposed for deterministic testing; production calls leave it
    None so it defaults to today's date.
    """
    if today is None:
        today = datetime.date.today()
    date_now = _date_now_str(today)

    with open(json_path) as f:
        content = f.read()
    data: PapersByKeyword = json.loads(content) if content else {}

    parts: list[str] = []
    if use_title and to_web:
        parts.append(_jekyll_front_matter())
    if show_badge:
        parts.append(_badge_shields())
    parts.append(_title_line(date_now, use_title))
    parts.append(_archive_link_line(archive_index_link))
    if use_tc:
        parts.append(_toc(data))
    for keyword, day_content in data.items():
        if not day_content:
            continue
        parts.append(_keyword_section(keyword, day_content, to_web=to_web, use_title=use_title, date_now=date_now))
    if show_badge:
        parts.append(_badge_link_definitions(f"{user_name}/{repo_name}"))

    with open(md_path, "w") as f:
        f.write("".join(parts))
    logging.info(f"{task} finished")


# Backward-compat name. Existing callers (and the daily_arxiv shim) import this.
json_to_md = render_index


def render_archive_pages(
    archive_json_dir: str,
    archive_md_dir: str,
    to_web: bool = False,
    show_badge: bool = False,
    user_name: str = "",
    repo_name: str = "",
    today: datetime.date | None = None,
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
        render_index(
            os.path.join(archive_json_dir, name),
            os.path.join(archive_md_dir, f"{stem}.md"),
            task=f"archive {stem}",
            to_web=to_web,
            show_badge=show_badge,
            user_name=user_name,
            repo_name=repo_name,
            today=today,
        )
        months.append(stem)

    _write_archive_index(archive_md_dir, months, to_web=to_web)


def _write_archive_index(archive_md_dir: str, months: list, to_web: bool = False) -> None:
    path = os.path.join(archive_md_dir, "index.md")
    months_desc = sorted(months, reverse=True)
    with open(path, "w") as f:
        if to_web:
            f.write(_jekyll_front_matter())
        f.write("# Archive\n\n")
        f.write("Older monthly snapshots.\n\n")
        f.write("| Month |\n|---|\n")
        for m in months_desc:
            f.write(f"| [{m}]({m}.md) |\n")
