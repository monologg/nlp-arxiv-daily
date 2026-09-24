// @ts-check
import { defineConfig } from "astro/config";
import sitemap from "@astrojs/sitemap";
import pagefind from "astro-pagefind";
import tailwindcss from "@tailwindcss/vite";

const isProd = process.env.NODE_ENV === "production";

// Production URL is https://monologg.kr/nlp-arxiv-daily/: GitHub Pages serves
// this project site under the account's custom domain, at the repo-name path
// it has always used, so existing external links keep working.
export default defineConfig({
  site: isProd ? "https://monologg.kr" : undefined,
  base: isProd ? "/nlp-arxiv-daily" : undefined,
  // Pagefind indexes "directory" outputs by default (`/foo/index.html`); the
  // integration's docs note `format: "file"` works too, but we stick with the
  // default since that's what GitHub Pages serves cleanest.
  output: "static",
  // pagefind() must run AFTER sitemap so it indexes the final dist tree.
  integrations: [sitemap(), pagefind()],
  vite: {
    plugins: [tailwindcss()],
  },
});
