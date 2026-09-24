/**
 * Site identity: the name used in page titles, the header, RSS channel
 * titles, OG images and BibTeX headers, plus the default description and the
 * repository link. A fork edits this file, `site` and `base` in
 * astro.config.mjs, and the few descriptions that still name the topic on
 * their own (footer, RSS, month pages; see the fork guide in README.md).
 */
export const SITE_NAME = "NLP Arxiv Daily";

/** Default meta description for pages that don't set their own. */
export const SITE_DESCRIPTION = "Daily-updated NLP arxiv paper digest";

/** Source repository, linked from the header. */
export const REPO_URL = "https://github.com/monologg/nlp-arxiv-daily";
