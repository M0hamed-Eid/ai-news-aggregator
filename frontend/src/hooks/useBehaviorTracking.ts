'use client';

// Behavioral instrumentation (M15 Phase 5) — React port of
// web/static/js/beacon.js, which only ever ran on the classic Django-
// rendered pages and had NO equivalent anywhere in the SPA (a real,
// silently-live gap found by the M15 Phase 5 audit: impression/click/
// dwell/scroll events feed app/tasks/affinity_tasks.py and
// profile_vector_tasks.py's real ranking-signal computation). Posts to the
// SAME existing endpoint (POST /behavior/events/, apps.behavior.views.
// EventIngestView) beacon.js already used — nothing server-side changes.
//
// Mirrors beacon.js's exact mechanism: a module-level queue flushed every
// 10s via a plain fetch(), or immediately via navigator.sendBeacon on
// visibilitychange/pagehide (the only transport that reliably fires on
// unload). Impressions are deduped per (contentType, contentId) for the
// life of the tab, same as beacon.js's seenImpressions Set.

import { useEffect, useRef } from 'react';
import { useAppStore } from '@/lib/store';
import { getCsrfToken } from '@/lib/api';

const EVENTS_URL = '/behavior/events/';
const FLUSH_INTERVAL_MS = 10000;

type BehaviorEvent =
  | { event_type: 'impression' | 'click'; content_type: 'article' | 'youtube_video'; content_id: number }
  | { event_type: 'dwell' | 'scroll'; value: number };

let queue: BehaviorEvent[] = [];
let flushTimerStarted = false;
const seenImpressions = new Set<string>();

function enqueue(event: BehaviorEvent) {
  queue.push(event);
}

function flush(useBeacon: boolean) {
  if (queue.length === 0) return;
  const payload = JSON.stringify({ events: queue.splice(0, queue.length) });
  if (useBeacon && typeof navigator !== 'undefined' && navigator.sendBeacon) {
    navigator.sendBeacon(EVENTS_URL, new Blob([payload], { type: 'application/json' }));
    return;
  }
  fetch(EVENTS_URL, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCsrfToken() },
    body: payload,
    keepalive: true,
    credentials: 'include',
  }).catch(() => {
    // best-effort telemetry — a dropped batch isn't worth retry logic,
    // matching beacon.js's own stated tradeoff.
  });
}

function ensureFlushTimer() {
  if (flushTimerStarted || typeof window === 'undefined') return;
  flushTimerStarted = true;
  setInterval(() => flush(false), FLUSH_INTERVAL_MS);
}

/** Fires one "click" event the first time this content is clicked from a
 * list context (ArticleCard/VideoCard's title) — a real engagement signal,
 * without adding a whole-card click handler that would change the Z.ai
 * design's interaction model (only specific elements are clickable there,
 * unlike the old Bootstrap cards where the entire card div was one
 * data-content-type/data-content-id click target). No-ops for anonymous
 * visitors, matching beacon.js's own top-level `if (!window.__AC_USER_ID)
 * return` bail (EventIngestView is login-required server-side anyway; this
 * just avoids a guaranteed-403 network call). */
export function trackClick(contentType: 'article' | 'youtube_video', contentId: number) {
  if (!useAppStore.getState().isLoggedIn) return;
  ensureFlushTimer();
  enqueue({ event_type: 'click', content_type: contentType, content_id: contentId });
}

/** Attach the returned ref to a card's root element to fire one
 * "impression" event the first time it's >=50% visible — same threshold
 * and dedup semantics as beacon.js's IntersectionObserver. No-ops for
 * anonymous visitors (see trackClick's identical note). */
export function useImpressionTracking(
  contentType: 'article' | 'youtube_video',
  contentId: number,
  enabled: boolean
) {
  const ref = useRef<HTMLDivElement | null>(null);
  const isLoggedIn = useAppStore((s) => s.isLoggedIn);

  useEffect(() => {
    if (!enabled || !isLoggedIn || typeof IntersectionObserver === 'undefined') return;
    const el = ref.current;
    if (!el) return;

    const key = `${contentType}:${contentId}`;
    if (seenImpressions.has(key)) return;

    ensureFlushTimer();
    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (!entry.isIntersecting) continue;
          if (!seenImpressions.has(key)) {
            seenImpressions.add(key);
            enqueue({ event_type: 'impression', content_type: contentType, content_id: contentId });
          }
          observer.disconnect();
        }
      },
      { threshold: 0.5 }
    );
    observer.observe(el);
    return () => observer.disconnect();
  }, [contentType, contentId, enabled, isLoggedIn]);

  return ref;
}

/** Page-level dwell time + max scroll depth — mount ONCE at the app shell
 * level (BehaviorTracker.tsx), not per-page-component. "dwell" is always
 * page-level, never per-item, matching beacon.js's own design (and this
 * project's established convention, see .wolf/cerebrum.md) — resets and
 * flushes on every SPA route change (currentPage), same boundary a real
 * classic Django page load used to provide. */
export function usePageDwellTracking() {
  const isLoggedIn = useAppStore((s) => s.isLoggedIn);
  const currentPage = useAppStore((s) => s.currentPage);
  const pageEnteredAtRef = useRef<number>(Date.now());
  const maxScrollDepthRef = useRef(0);

  useEffect(() => {
    if (!isLoggedIn) return;
    ensureFlushTimer();
    pageEnteredAtRef.current = Date.now();
    maxScrollDepthRef.current = 0;

    const onScroll = () => {
      const doc = document.documentElement;
      const scrolled = doc.scrollTop + doc.clientHeight;
      const pct = doc.scrollHeight ? Math.min(100, Math.round((scrolled / doc.scrollHeight) * 100)) : 0;
      if (pct > maxScrollDepthRef.current) maxScrollDepthRef.current = pct;
    };
    window.addEventListener('scroll', onScroll, { passive: true });

    const flushDwellAndScroll = () => {
      const dwellMs = Date.now() - pageEnteredAtRef.current;
      enqueue({ event_type: 'dwell', value: dwellMs });
      if (maxScrollDepthRef.current > 0) {
        enqueue({ event_type: 'scroll', value: maxScrollDepthRef.current });
      }
      flush(true);
    };

    const onVisibilityChange = () => {
      if (document.visibilityState === 'hidden') {
        flushDwellAndScroll();
      } else {
        pageEnteredAtRef.current = Date.now();
        maxScrollDepthRef.current = 0;
      }
    };
    document.addEventListener('visibilitychange', onVisibilityChange);
    window.addEventListener('pagehide', flushDwellAndScroll);

    return () => {
      // Route change (currentPage changed) or logout — ends this "page
      // view" exactly like a real navigation away from a classic Django page.
      flushDwellAndScroll();
      window.removeEventListener('scroll', onScroll);
      document.removeEventListener('visibilitychange', onVisibilityChange);
      window.removeEventListener('pagehide', flushDwellAndScroll);
    };
  }, [isLoggedIn, currentPage]);
}
