from __future__ import annotations

import logging

import yaml

from nlp_arxiv_daily.fetcher import fetch_papers
from nlp_arxiv_daily.renderer import json_to_md, render_archive_pages
from nlp_arxiv_daily.storage import write_papers_split


logging.basicConfig(format="[%(asctime)s %(levelname)s] %(message)s", datefmt="%m/%d/%Y %H:%M:%S", level=logging.INFO)


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


def get_daily_papers(topic, query="nlp", max_results=2):
    """
    Backward-compat adapter: fetch via `fetcher.fetch_papers`, then pre-render
    markdown rows in the legacy shape. Kept here because `demo()` still feeds
    its output back through `write_papers_split`.
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
