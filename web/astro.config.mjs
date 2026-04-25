// @ts-check
import { defineConfig } from "astro/config";
import sitemap from "@astrojs/sitemap";
import tailwindcss from "@tailwindcss/vite";

const isProd = process.env.NODE_ENV === "production";

// Custom domain (monologg.kr) is the production target. The repo is also
// deployed under the /nlp-arxiv-daily path historically, so we keep that
// base prefix to preserve external links once cutover happens (PRSL-77).
export default defineConfig({
  site: isProd ? "https://monologg.kr" : undefined,
  base: isProd ? "/nlp-arxiv-daily" : undefined,
  output: "static",
  integrations: [sitemap()],
  vite: {
    plugins: [tailwindcss()],
  },
});
