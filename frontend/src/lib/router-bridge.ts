// Bridges the Zustand store's imperative navigate()/goBack() calls to
// Next.js's real client-side router. Zustand actions aren't React
// components, so they can't call the useRouter() hook directly — a single
// <RouterBridge/> mounted once in the root layout captures the router
// instance here, and the store calls back into these plain functions.
'use client';

import type { useRouter } from 'next/navigation';

type Router = ReturnType<typeof useRouter>;

let routerInstance: Router | null = null;

export function setRouterInstance(router: Router) {
  routerInstance = router;
}

export function pushPath(path: string) {
  if (typeof window !== 'undefined' && window.location.pathname === path) return;
  if (routerInstance) {
    routerInstance.push(path);
  } else if (typeof window !== 'undefined') {
    window.location.href = path; // pre-hydration fallback
  }
}

export function goBackPath() {
  if (typeof window !== 'undefined') window.history.back();
}
