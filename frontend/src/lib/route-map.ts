// Maps a Zustand PageRoute (+ params) to a real, shareable URL and back.
// This is the ONLY place that knows about the URL shape — every page
// component still reads currentPage/pageParams from the store, unchanged.
import type { PageRoute } from './types';

export function routeToPath(page: PageRoute, params: Record<string, string> = {}): string {
  switch (page) {
    case 'home':
      return '/';
    case 'search':
      return '/search';
    case 'feed':
      return '/feed';
    case 'pricing':
      return '/pricing';
    case 'article-detail':
      return `/article/${params.id ?? ''}`;
    case 'video-detail':
      return `/video/${params.id ?? ''}`;
    case 'entity-profile':
      return `/entity/${params.id ?? ''}`;
    case 'sources':
      return '/sources';
    case 'people':
      return '/people';
    case 'insights':
      return '/insights';
    case 'library':
      return '/library';
    case 'profile':
      return '/profile';
    case 'billing':
      return '/billing';
    case 'preferences':
      return '/preferences';
    case 'onboarding':
      return '/onboarding';
    case 'login':
      return '/login';
    case 'signup':
      return '/signup';
    case 'forgot-password':
      return '/forgot-password';
    case 'password-reset-done':
      return '/password-reset-done';
    case 'story-cluster':
      return `/story/${params.type ?? ''}/${params.id ?? ''}`;
    case 'ops':
      return '/ops';
    case 'trending-stories':
      return '/trending';
    case 'terms':
      return '/terms';
    case 'privacy':
      return '/privacy';
    // password-reset-confirm / password-reset-complete / email-verify-done are
    // reached via an emailed link and stay classic Django server-rendered
    // pages entirely outside this SPA (see the integration plan) — no path
    // here is ever navigated to internally.
    default:
      return '/';
  }
}
