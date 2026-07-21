'use client';

import { useEffect } from 'react';
import { useQuery } from '@tanstack/react-query';
import { motion } from 'framer-motion';
import { ArrowLeft, Layers } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { api } from '@/lib/api';
import { useAppStore } from '@/lib/store';
import ArticleCard from '@/components/shared/ArticleCard';
import VideoCard from '@/components/shared/VideoCard';
import EmptyState from '@/components/shared/EmptyState';
import type { ContentItem } from '@/lib/types';

// GET /api/news/story/{content_type}/{content_id}/'s real JSON shape
// (web/apps/news/api_views.py::StoryClusterAPIView) — mirrors
// apps.news.views.StoryClusterView field-for-field. `items` includes the
// anchor item itself (same as get_full_story's own return value);
// `anchorId` is a type-prefixed id ("article-123"/"video-456") matching
// api.ts's parseContentRef convention, used to pick the anchor back out of
// `items` for the header.
interface StoryClusterResponse {
  anchorId: string;
  items: ContentItem[];
}

export default function StoryClusterPage() {
  const { pageParams, goBack, hydrateContentState } = useAppStore();
  const type = pageParams.type === 'video' ? 'video' : 'article';
  const id = pageParams.id || '';
  // The frontend's own short-form content type ('article'/'video') is used
  // in the URL/store params (matching ArticleCard/VideoCard's item.type),
  // but the Django endpoint takes the DB-facing content_type values.
  const djangoContentType = type === 'video' ? 'youtube_video' : 'article';

  const { data, isLoading, error } = useQuery({
    queryKey: ['story-cluster', djangoContentType, id],
    queryFn: () => api.get<StoryClusterResponse>(`/api/news/story/${djangoContentType}/${id}/`),
    enabled: !!id,
    retry: false,
  });

  useEffect(() => {
    if (data) hydrateContentState(data.items);
  }, [data, hydrateContentState]);

  if (isLoading) {
    return (
      <div className="mx-auto max-w-5xl px-4 py-6 md:px-6">
        <Skeleton className="mb-4 h-4 w-16" />
        <Skeleton className="mb-2 h-7 w-3/4" />
        <Skeleton className="mb-6 h-4 w-1/2" />
        <div className="space-y-3">
          <Skeleton className="h-24 w-full rounded-lg" />
          <Skeleton className="h-24 w-full rounded-lg" />
        </div>
      </div>
    );
  }

  if (!data || error) {
    return (
      <div className="mx-auto max-w-5xl px-4 py-16 text-center">
        <p className="text-ink-muted">This story couldn&apos;t be found.</p>
        <Button variant="link" onClick={goBack}>Go back</Button>
      </div>
    );
  }

  const anchor = data.items.find(item => item.id === data.anchorId) ?? data.items[0];

  return (
    <div className="mx-auto max-w-5xl px-4 py-6 md:px-6">
      <motion.div
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.3 }}
      >
        <button
          onClick={goBack}
          className="mb-4 flex items-center gap-1.5 text-sm text-ink-muted hover:text-ink transition-colors"
        >
          <ArrowLeft className="h-4 w-4" /> Back
        </button>

        <div className="mb-6 flex items-start gap-3">
          <div className="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-primary/10">
            <Layers className="h-4.5 w-4.5 text-primary" />
          </div>
          <div className="min-w-0">
            <h1 className="text-xl font-bold leading-snug tracking-tight text-ink">
              {anchor?.title ?? 'One story, all sources'}
            </h1>
            <p className="mt-1 text-sm text-ink-muted">
              {data.items.length > 1
                ? `Covered by ${data.items.length} sources — the same story, told across the corpus.`
                : 'Not currently grouped with any other coverage.'}
            </p>
          </div>
        </div>

        {data.items.length > 0 ? (
          <div className="space-y-3">
            {data.items.map(item => (
              item.type === 'video' ? (
                <VideoCard key={item.id} item={item} />
              ) : (
                <ArticleCard key={item.id} item={item} />
              )
            ))}
          </div>
        ) : (
          <EmptyState
            icon={Layers}
            title="Not clustered yet"
            description="This item hasn't been grouped with anything else — clustering runs alongside every scrape and may not have processed it yet."
          />
        )}
      </motion.div>
    </div>
  );
}
