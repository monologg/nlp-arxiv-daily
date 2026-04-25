import { defineCollection, z } from "astro:content";
import { glob } from "astro/loaders";

// Each archive JSON file (docs/archive-web/YYYY-MM.json) is shaped as
// {keyword: {paper_id: row_string}}. `row_string` is a one-line markdown
// snippet emitted by the Python pipeline; PRSL-72 parses it back into
// structured fields. Here we just validate the shape.
export const paperBucketSchema = z.record(z.string(), z.record(z.string(), z.string()));

const archive = defineCollection({
  loader: glob({
    base: "../docs/archive-web",
    pattern: "*.json",
  }),
  schema: paperBucketSchema,
});

export const collections = { archive };
