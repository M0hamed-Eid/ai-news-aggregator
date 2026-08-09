import type { NextConfig } from "next";

// Local dev only: proxy every existing Django URL prefix to the Django
// runserver (127.0.0.1:8000) so `npm run dev` "just works" without Caddy —
// mirrors the path-based split Caddy performs in production (see
// docker/Caddyfile), just expressed as Next.js rewrites instead. In
// production the standalone server never runs these; Caddy routes directly
// to each container, so this only applies in dev.
const DJANGO_DEV_ORIGIN = process.env.DJANGO_DEV_ORIGIN || "http://127.0.0.1:8000";
// M15 Phase 5 retired the classic (non-API) apps.news/apps.onboarding
// template routes entirely — those apps' real JSON APIs live under
// /api/news/* and /api/onboarding/* (already covered by /api), so bare
// /news and /onboarding are no longer Django-owned at all. Keep this list
// in sync with docker/Caddyfile's @django_paths, which proxies the exact
// same set in production.
const DJANGO_PREFIXES = [
  "/api",
  "/admin",
  "/accounts",
  "/behavior",
  "/assistant",
  "/healthz",
  "/r",
  "/static",
];

const nextConfig: NextConfig = {
  typescript: {
    ignoreBuildErrors: true,
  },
  reactStrictMode: false,
  // Every Django URL this app owns ends in a trailing slash (its own
  // APPEND_SLASH convention, matching every existing urls.py in web/apps/*).
  // Without this, Next's default trailing-slash redirect (/api/session/ ->
  // /api/session, 308) and Django's APPEND_SLASH redirect (the reverse)
  // fight each other through the rewrite below and infinite-loop —
  // confirmed live via `curl -v`. skipTrailingSlashRedirect lets a request's
  // original trailing slash pass through the rewrite unchanged.
  skipTrailingSlashRedirect: true,
  async rewrites() {
    if (process.env.NODE_ENV !== "development") return [];
    // Two rules per prefix, trailing-slash variant FIRST (first match
    // wins): `:path*`'s destination reconstruction drops a trailing slash
    // regardless of skipTrailingSlashRedirect above (confirmed live — a
    // request for /api/session/ reached Django's runserver as /api/session,
    // which then 301-redirected back to /api/session/, relayed verbatim
    // through the rewrite -> infinite loop). Matching a literal trailing
    // "/" in `source` and putting one back in `destination` (outside the
    // wildcard) preserves it exactly for URLs that have one, while the
    // second rule still covers extension-bearing paths that never carry a
    // trailing slash (e.g. /static/css/app.css).
    return DJANGO_PREFIXES.flatMap((prefix) => [
      {
        source: `${prefix}/:path*/`,
        destination: `${DJANGO_DEV_ORIGIN}${prefix}/:path*/`,
      },
      {
        source: `${prefix}/:path*`,
        destination: `${DJANGO_DEV_ORIGIN}${prefix}/:path*`,
      },
    ]);
  },
};

export default nextConfig;
