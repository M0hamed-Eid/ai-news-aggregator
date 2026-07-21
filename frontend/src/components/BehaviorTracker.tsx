'use client';

import { usePageDwellTracking } from '@/hooks/useBehaviorTracking';

// Mounted once in layout.tsx (same pattern as RouterBridge/SessionHydrator)
// — real page-level dwell + scroll telemetry, replacing web/static/js/
// beacon.js's equivalent for the SPA (see useBehaviorTracking.ts's own
// docstring for why this existed as a real, unmigrated gap). Renders nothing.
export default function BehaviorTracker() {
  usePageDwellTracking();
  return null;
}
