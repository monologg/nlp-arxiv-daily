from __future__ import annotations

import logging

import yaml

from nlp_arxiv_daily.fetcher import fetch_papers


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

    with open(config_file) as f:
        config = yaml.load(f, Loader=yaml.FullLoader)
        config["kv"] = pretty_filters(**config)
        logging.info(f"config = {config}")
    return config


def get_daily_papers(topic, query="nlp", max_results=2):
    """
    Backward-compat adapter: fetch via `fetcher.fetch_papers`, then pre-render
    markdown rows in the legacy shape. Used by `cli.cmd_fetch` to keep the
    JSON files in the existing format the renderer expects.
    """
    papers = fetch_papers(query=query, max_results=max_results)

    content: dict[str, str] = {}
    content_to_web: dict[str, str] = {}
    for p in papers:
        code_md = f"**[link]({p.code_link})**" if p.code_link else "null"
        content[p.paper_id] = (
            f"|**{p.update_time}**|**{p.title}**|{p.first_author} et.al.|[{p.arxiv_short_id}]({p.paper_url})|{code_md}|\n"
        )
        web_line = f"- {p.update_time}, **{p.title}**, {p.first_author} et.al., Paper: [{p.paper_url}]({p.paper_url})"
        if p.code_link:
            web_line += f", Code: **[{p.code_link}]({p.code_link})**"
        content_to_web[p.paper_id] = web_line + "\n"

    return {topic: content}, {topic: content_to_web}


def demo(**config) -> None:
    """Backward-compat alias for `cli.cmd_run`. Prefer the CLI entrypoint."""
    from nlp_arxiv_daily.cli import cmd_run

    cmd_run(config)
