// Shared CSRF-cookie-aware fetch wrapper for every real backend call.
// Mirrors the exact getCsrfToken() convention already used by
// web/static/js/beacon.js and assistant.js — the `csrftoken` cookie is set
// by Django (see GET /api/session/, apps.accounts.api_views.SessionView)
// and echoed back as the X-CSRFToken header on any mutating request.
//
// M16 — split-domain deploy: when NEXT_PUBLIC_API_BASE_URL is unset (the
// Oracle path, where Caddy/next.config.ts rewrites() make Django appear
// same-origin, and local dev), every call below stays a bare relative path
// with EXACTLY today's behavior — zero config, zero risk of regressing the
// working deployment. Only a Vercel+Render split sets this env var, which
// makes fetch() target Django's real cross-origin URL. Cross-origin
// `credentials:'include'` cookie auth then depends on Django's matching
// CORS_ALLOWED_ORIGINS/CORS_ALLOW_CREDENTIALS/SameSite=None config (see
// web/config/settings/prod.py) — this file's only job is building the
// right URL, not deciding whether cookies are allowed to travel.
const API_BASE_URL = (process.env.NEXT_PUBLIC_API_BASE_URL ?? '').replace(/\/+$/, '');

export function apiUrl(path: string): string {
  return API_BASE_URL ? `${API_BASE_URL}${path}` : path;
}

// M16 split-domain fix — on the Vercel+Render split, the csrftoken cookie
// Django sets is scoped to the Render domain, so document.cookie on a
// vercel.app page can never read it (cross-site cookie ATTACHMENT on
// outgoing fetches still works fine via credentials:'include'+SameSite=
// None; this is purely about JS being unable to READ a cookie set for a
// different registrable domain). SessionHydrator.tsx caches the token
// value from GET /api/session/'s JSON body (see SessionResponse.csrfToken,
// web/apps/accounts/api_views.py::_session_payload) via setCsrfToken() the
// moment the app loads, so this override is populated before any mutating
// request could plausibly fire. Falls back to the cookie read for the
// same-origin Oracle/local-dev path, where it works today and needs no
// change.
let csrfTokenOverride: string | null = null;

export function setCsrfToken(token: string | null): void {
  csrfTokenOverride = token;
}

// Exported (not just used internally) so assistant-stream.ts's raw
// fetch()+ReadableStream SSE call — which can't go through the request()
// wrapper below, since that assumes a JSON response — can still send the
// same X-CSRFToken header every other mutating request does.
export function getCsrfToken(): string {
  if (csrfTokenOverride) return csrfTokenOverride;
  if (typeof document === 'undefined') return '';
  const match = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
  return match ? decodeURIComponent(match[1]) : '';
}

export class ApiError extends Error {
  status: number;
  body: unknown;

  constructor(status: number, body: unknown, message?: string) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.body = body;
  }
}

type RequestOptions = Omit<RequestInit, 'body'> & { body?: unknown };

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { body, headers, method = 'GET', ...rest } = options;
  const isMutating = method !== 'GET' && method !== 'HEAD';

  const res = await fetch(apiUrl(path), {
    ...rest,
    method,
    credentials: 'include',
    // Every response here is per-user/per-session dynamic data — the
    // browser's HTTP cache must never serve a stale one. This also sidesteps
    // a nasty dev-only trap: a 301 (like Django's APPEND_SLASH redirect)
    // gets cached by the browser INDEFINITELY, origin-scoped rather than
    // tab-scoped — confirmed live, a stale cached redirect from a since-fixed
    // next.config.ts bug kept reappearing as a phantom failed request on
    // fresh page loads/new tabs until this was added.
    cache: rest.cache ?? 'no-store',
    headers: {
      'Content-Type': 'application/json',
      ...(isMutating ? { 'X-CSRFToken': getCsrfToken() } : {}),
      ...headers,
    },
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });

  const contentType = res.headers.get('content-type') || '';
  const data = contentType.includes('application/json') ? await res.json().catch(() => null) : null;

  // Every endpoint that returns a session-shaped payload (session/login/
  // signup/logout/accept-terms — see _session_payload) carries a fresh
  // csrfToken; opportunistically refresh the in-memory override any time
  // one shows up, so the token used for the NEXT mutating call is never
  // stale relative to the one Django most recently issued.
  if (data && typeof data === 'object' && typeof (data as { csrfToken?: unknown }).csrfToken === 'string') {
    setCsrfToken((data as { csrfToken: string }).csrfToken);
  }

  if (!res.ok) {
    const message = (data && typeof data === 'object' && 'error' in data && String((data as { error: unknown }).error)) || res.statusText;
    throw new ApiError(res.status, data, message);
  }
  return data as T;
}

export const api = {
  get: <T>(path: string, options?: RequestOptions) => request<T>(path, { ...options, method: 'GET' }),
  post: <T>(path: string, body?: unknown, options?: RequestOptions) => request<T>(path, { ...options, method: 'POST', body }),
  put: <T>(path: string, body?: unknown, options?: RequestOptions) => request<T>(path, { ...options, method: 'PUT', body }),
  patch: <T>(path: string, body?: unknown, options?: RequestOptions) => request<T>(path, { ...options, method: 'PATCH', body }),
  delete: <T>(path: string, options?: RequestOptions) => request<T>(path, { ...options, method: 'DELETE' }),
};

// Matches web/apps/accounts/api_views.py::SessionView's JSON shape exactly.
export interface SessionUser {
  id: number;
  email: string;
  firstName: string;
  plan: 'free' | 'pro';
  isStaff: boolean;
  emailVerified: boolean;
  onboardingCompleted: boolean;
}

export interface SessionResponse {
  isAuthenticated: boolean;
  user: SessionUser | null;
  entitlements: Record<string, boolean>;
  csrfToken: string;
}

export function getSession(): Promise<SessionResponse> {
  return api.get<SessionResponse>('/api/session/');
}

// Frontend content ids are type-prefixed ("article-123" / "video-456" —
// see web/apps/news/serializers.py's serialize_item docstring for why:
// Article and YoutubeVideo have independent auto-increment pks, so a bare
// numeric id would let an article and a video collide in any id-keyed
// client state). This is the one place that decodes a frontend id back
// into what apps.behavior's save/hide/follow endpoints expect.
export function parseContentRef(id: string): { contentType: 'article' | 'youtube_video'; contentId: number } | null {
  const [prefix, rest] = id.split(/-(.+)/);
  const contentId = Number(rest);
  if (!Number.isFinite(contentId)) return null;
  if (prefix === 'article') return { contentType: 'article', contentId };
  if (prefix === 'video') return { contentType: 'youtube_video', contentId };
  return null;
}

export function toggleSaved(contentType: 'article' | 'youtube_video', contentId: number): Promise<{ is_saved: boolean }> {
  return api.post('/behavior/save/', { content_type: contentType, content_id: contentId });
}

export function toggleHidden(contentType: 'article' | 'youtube_video', contentId: number): Promise<{ is_hidden: boolean }> {
  return api.post('/behavior/hide/', { content_type: contentType, content_id: contentId });
}

// Real follow/unfollow (M15 Phase 5 — web/apps/behavior/api_views.py).
// targetKey for 'topic' is a display NAME (TopicTag), never a slug — the
// backend resolves name -> TaxonomyTopic.slug itself before storage.
export interface FollowsState {
  followedEntityIds: string[];
  followedTopicNames: string[];
}

export function getFollowsState(): Promise<FollowsState> {
  return api.get<FollowsState>('/api/behavior/follows/');
}

export function toggleFollow(targetType: 'entity' | 'topic', targetKey: string): Promise<{ following: boolean }> {
  return api.post('/api/behavior/follow/', { targetType, targetKey });
}
