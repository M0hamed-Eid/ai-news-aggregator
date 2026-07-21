'use client';

import { useEffect } from 'react';
import { getSession, getFollowsState } from '@/lib/api';
import { useAppStore } from '@/lib/store';

// Mounted once in layout.tsx (same pattern as RouterBridge) — calls the
// real GET /api/session/ on app load and reconciles Zustand's isLoggedIn/
// user with the actual Django session cookie, replacing what used to be a
// hardcoded logged-in mock user (see store.ts's AuthState). Renders nothing.
export default function SessionHydrator() {
  const hydrateSession = useAppStore((state) => state.hydrateSession);
  const hydrateFollows = useAppStore((state) => state.hydrateFollows);

  useEffect(() => {
    let cancelled = false;
    getSession()
      .then((session) => {
        if (cancelled) return;
        hydrateSession(session.isAuthenticated ? session.user : null);
        // GET /api/behavior/follows/ is LoginRequiredMixin-gated — only
        // fetch it once we know the session is real, not on every anonymous
        // page load.
        if (session.isAuthenticated) {
          getFollowsState()
            .then((follows) => {
              if (!cancelled) hydrateFollows(follows.followedEntityIds, follows.followedTopicNames);
            })
            .catch(() => {});
        }
      })
      .catch(() => {
        if (!cancelled) hydrateSession(null);
      });
    return () => {
      cancelled = true;
    };
  }, [hydrateSession, hydrateFollows]);

  return null;
}
