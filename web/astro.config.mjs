// @ts-check
import { defineConfig } from "astro/config";
import sitemap from "@astrojs/sitemap";
import pagefind from "astro-pagefind";
import tailwindcss from "@tailwindcss/vite";

const isProd = process.env.NODE_ENV === "production";

// Custom domain (monologg.kr) is the production target. The repo is also
// deployed under the /nlp-arxiv-daily path historically, so we keep that
// base prefix to preserve external links once cutover happens (PRSL-77).
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
