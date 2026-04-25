import argparse

from nlp_arxiv_daily.core import demo, load_config


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config_path", type=str, default="config.yaml", help="configuration file path")
    args = parser.parse_args()
    config = load_config(args.config_path)
    demo(**config)


if __name__ == "__main__":
    main()
