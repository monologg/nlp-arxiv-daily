from __future__ import annotations

import logging

import yaml

from nlp_arxiv_daily.fetcher import fetch_papers
from nlp_arxiv_daily.records import paper_to_web_record
from nlp_arxiv_daily.types import Paper, PaperValue


logging.basicConfig(format="[%(asctime)s %(levelname)s] %(message)s", datefmt="%m/%d/%Y %H:%M:%S", level=logging.INFO)


def papers_to_legacy_rows(papers: list[Paper], topic: str) -> tuple[dict, dict]:
    """Render a list[Paper] into ({topic: {paper_id: row}}, {topic: {paper_id: record}}).

    The README flavor keeps its pipe-table markdown row. The gitpage (web)
    flavor is a structured `WebRecord` dict. (The Astro site still parses the
    older one-line string rows too, though this repo's data no longer has any.)

    Shared by `cli.cmd_fetch` (daily cron), `cli.cmd_backfill` and
    `get_daily_papers` so all of them persist data in the same JSON shape.
    """
    content: dict[str, str] = {}
    content_to_web: dict[str, PaperValue] = {}
    for p in papers:
        code_md = f"**[link]({p.code_link})**" if p.code_link else "null"
        content[p.paper_id] = (
            f"|**{p.update_time}**|**{p.title}**|{p.first_author} et.al."
            f"|[{p.arxiv_short_id}]({p.paper_url})|{code_md}|\n"
        )
        content_to_web[p.paper_id] = paper_to_web_record(p)

    return {topic: content}, {topic: content_to_web}


def load_config(config_file: str) -> dict:
    """
    config_file: input config file path
    return: a dict of configuration
    """

    # make filters pretty
    def pretty_filters(**config) -> dict:
        keywords = {}
        EXCAPE = '"'
        # Explicit field prefix. arxiv defaults a bare term to an all-field
        # search anyway, but only an explicit `all:` makes the query parser
        # deterministic — a bare `NLP OR "..."` can be mis-grouped, which
        # silently returns the wrong set (or nothing) and feeds the 429 retry
        # storm. Prefixing every term sidesteps the parser's guesswork.
        FIELD = "all:"
        # Whitespace around OR is required — arxiv parses `NLPOR"..."` as a
        # single token, which yields no results and triggers 429s on retry.
        OR = " OR "

        def parse_filters(filters: list):
            ret = ""
            for idx in range(0, len(filters)):
                filter = filters[idx]
                if len(filter.split()) > 1:
                    ret += FIELD + EXCAPE + filter + EXCAPE
                else:
                    ret += FIELD + filter
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
    Backward-compat adapter: fetch via `fetcher.fetch_papers` (the old top-N
    newest-first query), then pre-render rows with `papers_to_legacy_rows`.
    Nothing in the pipeline calls it any more — `cli.cmd_fetch` uses
    `fetcher.fetch_recent_papers` — it is kept only as a public export.
    """
    papers = fetch_papers(query=query, max_results=max_results)
    return papers_to_legacy_rows(papers, topic)


def demo(**config) -> None:
    """Backward-compat alias for `cli.cmd_run`. Prefer the CLI entrypoint."""
    from nlp_arxiv_daily.cli import cmd_run

    cmd_run(config)
