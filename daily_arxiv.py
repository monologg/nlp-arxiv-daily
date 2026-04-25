import argparse
import datetime
import json
import logging
import re

import arxiv
import yaml


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


def get_authors(authors, first_author=False):
    output = str()
    if first_author is False:
        output = ", ".join(str(author) for author in authors)
    else:
        output = authors[0]
    return output


def sort_papers(papers):
    output = {}
    keys = list(papers.keys())
    keys.sort(reverse=True)
    for key in keys:
        output[key] = papers[key]
    return output


def get_daily_papers(topic, query="nlp", max_results=2):
    """
    @param topic: str
    @param query: str
    @return paper_with_code: dict
    """
    content = {}
    content_to_web = {}
    client = arxiv.Client()
    search = arxiv.Search(query=query, max_results=max_results, sort_by=arxiv.SortCriterion.SubmittedDate)

    for result in client.results(search):
        paper_id = result.get_short_id()
        paper_title = result.title
        paper_url = result.entry_id
        paper_first_author = get_authors(result.authors, first_author=True)
        update_time = result.updated.date()

        logging.info(f"Time = {update_time} title = {paper_title} author = {paper_first_author}")

        # eg: 2108.09112v1 -> 2108.09112
        ver_pos = paper_id.find("v")
        if ver_pos == -1:
            paper_key = paper_id
        else:
            paper_key = paper_id[0:ver_pos]

        # Code 컬럼은 항상 |null| — paperswithcode 종료 후 lookup 소스 없음.
        # 기존 JSON 의 [link] 가 있는 행과 한 테이블에 섞여도 컬럼 수가 일치해 렌더링 OK.
        content[paper_key] = "|**{}**|**{}**|{} et.al.|[{}]({})|null|\n".format(
            update_time, paper_title, paper_first_author, paper_id, paper_url
        )
        content_to_web[paper_key] = "- {}, **{}**, {} et.al., Paper: [{}]({})\n".format(
            update_time, paper_title, paper_first_author, paper_url, paper_url
        )

    data = {topic: content}
    data_web = {topic: content_to_web}
    return data, data_web


def update_json_file(filename, data_dict):
    """
    daily update json file using data_dict
    """
    with open(filename, "r") as f:
        content = f.read()
        if not content:
            m = {}
        else:
            m = json.loads(content)

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


def json_to_md(filename, md_filename, task="", to_web=False, use_title=True, use_tc=True, show_badge=True):
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
        if not content:
            data = {}
        else:
            data = json.loads(content)

    # clean README.md if daily already exist else create it
    with open(md_filename, "w+") as f:
        pass

    # write data into README.md
    with open(md_filename, "a+") as f:
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

            if use_title is True:
                if to_web is False:
                    f.write("|Publish Date|Title|Authors|PDF|Code|\n" + "|---|---|---|---|---|\n")
                else:
                    f.write("| Publish Date | Title | Authors | PDF | Code |\n")
                    f.write("|:---------|:-----------------------|:---------|:------|:------|\n")

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
                (
                    "[contributors-shield]: https://img.shields.io/github/"
                    "contributors/monologg/nlp-arxiv-daily.svg?style=for-the-badge\n"
                )
            )
            f.write(("[contributors-url]: https://github.com/monologg/nlp-arxiv-daily/graphs/contributors\n"))
            f.write(
                (
                    "[forks-shield]: https://img.shields.io/github/forks/monologg/"
                    "nlp-arxiv-daily.svg?style=for-the-badge\n"
                )
            )
            f.write(("[forks-url]: https://github.com/monologg/nlp-arxiv-daily/network/members\n"))
            f.write(
                (
                    "[stars-shield]: https://img.shields.io/github/stars/monologg/"
                    "nlp-arxiv-daily.svg?style=for-the-badge\n"
                )
            )
            f.write(("[stars-url]: https://github.com/monologg/nlp-arxiv-daily/stargazers\n"))
            f.write(
                (
                    "[issues-shield]: https://img.shields.io/github/issues/monologg/"
                    "nlp-arxiv-daily.svg?style=for-the-badge\n"
                )
            )
            f.write(("[issues-url]: https://github.com/monologg/nlp-arxiv-daily/issues\n\n"))

    logging.info(f"{task} finished")


def demo(**config):
    data_collector = []
    data_collector_web = []

    keywords = config["kv"]
    max_results = config["max_results"]
    publish_readme = config["publish_readme"]
    publish_gitpage = config["publish_gitpage"]
    show_badge = config["show_badge"]

    logging.info("GET daily papers begin")
    for topic, keyword in keywords.items():
        logging.info(f"Keyword: {topic}")
        data, data_web = get_daily_papers(topic, query=keyword, max_results=max_results)
        data_collector.append(data)
        data_collector_web.append(data_web)
        print("\n")
    logging.info("GET daily papers end")

    # 1. update README.md file
    if publish_readme:
        json_file = config["json_readme_path"]
        md_file = config["md_readme_path"]
        update_json_file(json_file, data_collector)
        json_to_md(json_file, md_file, task="Update Readme", show_badge=show_badge)

    # 2. update docs/index.md file (to gitpage)
    if publish_gitpage:
        json_file = config["json_gitpage_path"]
        md_file = config["md_gitpage_path"]
        update_json_file(json_file, data_collector)
        json_to_md(json_file, md_file, task="Update GitPage", to_web=True, show_badge=show_badge)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--config_path", type=str, default="config.yaml", help="configuration file path")
    args = parser.parse_args()
    config = load_config(args.config_path)
    demo(**config)
