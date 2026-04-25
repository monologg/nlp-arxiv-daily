/**
 * Prefix an absolute path with `import.meta.env.BASE_URL` so links work
 * both at the dev root (`/`) and the prod subpath (`/nlp-arxiv-daily/`).
 *
 * Always pass paths starting with `/`; the helper trims the trailing slash
 * of the base before concatenating to avoid `//` artifacts.
 */
export function withBase(path: string): string {
  const base = import.meta.env.BASE_URL.replace(/\/$/, "");
  return `${base}${path}`;
}
