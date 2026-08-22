import type { NextConfig } from "next";

// Local dev: proxy every existing Django URL prefix to the Django runserver
// (127.0.0.1:8000) so `npm run dev` "just works" without Caddy — mirrors the
// path-based split Caddy performs in production (see docker/Caddyfile),
// just expressed as Next.js rewrites instead.
const DJANGO_DEV_ORIGIN = process.env.DJANGO_DEV_ORIGIN || "http://127.0.0.1:8000";

// Production, IP-only backend (no domain, see docker/Caddyfile's plain-HTTP
// header comment for why): when BACKEND_ORIGIN is set (e.g.
// "http://<ec2-ip>"), Vercel's own Next.js server proxies these same
// prefixes to it SERVER-SIDE, so the browser only ever talks to this app's
// own HTTPS domain — never the backend directly. That's what makes an
// HTTP-only backend safe to call: browsers block an HTTPS page from calling
// plain HTTP directly (mixed content), but a server-to-server proxy call
// isn't a browser request and isn't subject to that rule at all.
// NEXT_PUBLIC_API_BASE_URL must be UNSET for this path — see lib/api.ts's
// own comment on the same fork. Leave BACKEND_ORIGIN unset (as before) to
// keep today's direct-cross-origin-via-NEXT_PUBLIC_API_BASE_URL behavior
// working unchanged.
const BACKEND_ORIGIN = process.env.BACKEND_ORIGIN || "";
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
    // Dev always proxies to the local runserver. Production only proxies
    // when BACKEND_ORIGIN is explicitly set (the IP-only backend path);
    // otherwise production returns [] unchanged, exactly as before, so the
    // direct-cross-origin-via-NEXT_PUBLIC_API_BASE_URL path keeps working
    // with zero risk of regressing it.
    const origin = process.env.NODE_ENV === "development" ? DJANGO_DEV_ORIGIN : BACKEND_ORIGIN;
    if (!origin) return [];
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
        destination: `${origin}${prefix}/:path*/`,
      },
      {
        source: `${prefix}/:path*`,
        destination: `${origin}${prefix}/:path*`,
      },
    ]);
  },
};

export default nextConfig;
