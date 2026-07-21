'use client';

import { motion } from 'framer-motion';
import { useQuery } from '@tanstack/react-query';
import { Lightbulb, Sparkles, ExternalLink, Shield } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Separator } from '@/components/ui/separator';
import { Skeleton } from '@/components/ui/skeleton';
import { format } from 'date-fns';
import { useAppStore } from '@/lib/store';
import { api, parseContentRef } from '@/lib/api';
import EmptyState from '@/components/shared/EmptyState';

// GET /api/news/insights/'s real JSON shape (web/apps/news/api_views.py::
// InsightsAPIView) — mirrors apps.news.views.TrendReportView field-for-
// field: same user_can(..., "trend_narrative") gate, same TrendReport
// query, same resolve_narrative_citations() call. Each source's `id` is a
// type-prefixed content ref ("article-123"/"video-456", api.ts's
// parseContentRef convention) rather than a bare url, since these are
// always internal corpus items, never external links.
interface InsightsResponse {
  canView: boolean;
  weekOf: string | null;
  generatedAt: string | null;
  insights: { id: string; headline: string; summary: string; sources: { id: string; title: string }[] }[];
}

export default function InsightsPage() {
  const { navigate, isLoggedIn, user } = useAppStore();

  const { data, isLoading } = useQuery({
    queryKey: ['insights'],
    queryFn: () => api.get<InsightsResponse>('/api/news/insights/'),
    enabled: isLoggedIn && user?.plan === 'pro',
  });

  if (!isLoggedIn) {
    return (
      <div className="mx-auto max-w-3xl px-4 py-16 md:px-6">
        <div className="flex flex-col items-center justify-center py-16 text-center">
          <div className="mb-4 flex h-16 w-16 items-center justify-center rounded-2xl bg-muted">
            <Lightbulb className="h-8 w-8 text-ink-muted" />
          </div>
          <h3 className="mb-1 text-lg font-semibold text-ink">Sign in to see Insights</h3>
          <p className="mb-6 max-w-sm text-sm text-ink-muted">
            Weekly trend briefings are available after signing in.
          </p>
          <Button onClick={() => navigate('login')}>Log in</Button>
        </div>
      </div>
    );
  }

  if (user?.plan !== 'pro') {
    return (
      <div className="mx-auto max-w-3xl px-4 py-16 md:px-6">
        <motion.div
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.3 }}
          className="rounded-2xl border-2 border-primary/20 bg-primary/5 p-8 text-center"
        >
          <div className="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-2xl bg-primary/10">
            <Shield className="h-8 w-8 text-primary" />
          </div>
          <h2 className="mb-2 text-xl font-bold text-ink">Insights is a Pro feature</h2>
          <p className="mx-auto mb-6 max-w-sm text-sm text-ink-muted">
            Get weekly AI trend briefings with curated analysis and source links. Upgrade to unlock.
          </p>
          <div className="mb-6 text-left max-w-sm mx-auto space-y-2">
            <div className="flex items-center gap-2 text-sm text-ink-muted">
              <Sparkles className="h-4 w-4 text-primary" /> Weekly trend analysis
            </div>
            <div className="flex items-center gap-2 text-sm text-ink-muted">
              <Sparkles className="h-4 w-4 text-primary" /> Curated source links
            </div>
            <div className="flex items-center gap-2 text-sm text-ink-muted">
              <Sparkles className="h-4 w-4 text-primary" /> Pattern recognition across sources
            </div>
          </div>
          <Button onClick={() => navigate('pricing')}>
            <Sparkles className="mr-2 h-4 w-4" /> Upgrade to Pro
          </Button>
        </motion.div>
      </div>
    );
  }

  if (isLoading || !data) {
    return (
      <div className="mx-auto max-w-5xl px-4 py-6 md:px-6">
        <Skeleton className="mb-6 h-4 w-40" />
        <div className="space-y-4">
          <Skeleton className="h-40 w-full rounded-xl" />
          <Skeleton className="h-40 w-full rounded-xl" />
        </div>
      </div>
    );
  }

  if (data.insights.length === 0) {
    return (
      <div className="mx-auto max-w-3xl px-4 py-16 md:px-6">
        <EmptyState
          icon={Lightbulb}
          title={data.weekOf ? 'No insights yet' : 'No report yet'}
          description={
            data.weekOf
              ? "Nothing trended strongly enough last week to write a grounded briefing about."
              : "The first weekly briefing hasn't been generated yet — check back soon."
          }
        />
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-5xl px-4 py-6 md:px-6">
      <motion.div
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.3 }}
      >
        {data.insights.map((insight, i) => (
          <div key={insight.id} className={i > 0 ? 'mt-8' : ''}>
            {i === 0 && data.weekOf && (
              <div className="mb-6">
                <h2 className="text-sm font-semibold text-ink-muted uppercase tracking-wider">
                  Week of {format(new Date(data.weekOf), 'MMM d, yyyy')}
                </h2>
              </div>
            )}

            <div className="rounded-xl border border-border bg-card p-5">
              <h3 className="mb-2 text-lg font-semibold text-ink">{insight.headline}</h3>
              <p className="mb-4 text-sm leading-relaxed text-ink-muted">{insight.summary}</p>
              {insight.sources.length > 0 && (
                <>
                  <Separator className="mb-3" />
                  <h4 className="mb-2 text-xs font-semibold text-ink-muted uppercase tracking-wider">Sources</h4>
                  <ul className="space-y-1.5">
                    {insight.sources.map((src) => {
                      const ref = parseContentRef(src.id);
                      return (
                        <li key={src.id}>
                          <button
                            onClick={() => ref && navigate(ref.contentType === 'youtube_video' ? 'video-detail' : 'article-detail', { id: src.id })}
                            className="flex items-center gap-1.5 text-sm text-primary hover:underline"
                          >
                            <ExternalLink className="h-3 w-3" />
                            {src.title}
                          </button>
                        </li>
                      );
                    })}
                  </ul>
                </>
              )}
            </div>
          </div>
        ))}
      </motion.div>
    </div>
  );
}