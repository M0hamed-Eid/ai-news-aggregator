'use client';

import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { motion } from 'framer-motion';
import { Flame, ArrowRight } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { formatDistanceToNow } from 'date-fns';
import { useAppStore } from '@/lib/store';
import { api, parseContentRef } from '@/lib/api';
import EmptyState from '@/components/shared/EmptyState';
import type { ContentItem } from '@/lib/types';

// GET /api/news/clusters/?hours=... 's real JSON shape
// (web/apps/news/api_views.py::ClusterListAPIView) — mirrors
// apps.news.views.ClusterListView field-for-field (same get_hot_clusters()
// call, same hour-window presets). Recreated in M15 Phase 5: the old
// news/cluster_list.html had zero SPA equivalent -- StoryClusterPage.tsx
// only ever shows ONE already-known cluster, it was never a discovery
// surface on its own.
interface HourPreset {
  hours: number;
  label: string;
}

interface HotCluster {
  memberCount: number;
  representative: ContentItem;
}

interface ClusterListResponse {
  activeHours: number;
  hourPresets: HourPreset[];
  clusters: HotCluster[];
}

export default function TrendingStoriesPage() {
  const { navigate, isLoggedIn } = useAppStore();
  const [hours, setHours] = useState(168);

  const { data, isLoading } = useQuery({
    queryKey: ['clusters', hours],
    queryFn: () => api.get<ClusterListResponse>(`/api/news/clusters/?hours=${hours}`),
    enabled: isLoggedIn,
  });

  if (!isLoggedIn) {
    return (
      <div className="mx-auto max-w-3xl px-4 py-16 md:px-6">
        <EmptyState
          icon={Flame}
          title="Sign in to see trending stories"
          description="See which stories multiple sources are covering at once."
          action={{ label: 'Log in', onClick: () => navigate('login') }}
        />
      </div>
    );
  }

  const presets = data?.hourPresets ?? [
    { hours: 48, label: 'Last 48 hours' },
    { hours: 168, label: 'Last 7 days' },
    { hours: 720, label: 'Last 30 days' },
  ];

  return (
    <div className="mx-auto max-w-5xl px-4 py-6 md:px-6">
      <motion.div
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.3 }}
      >
        <div className="mb-2 flex items-center gap-2.5">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-orange-100 dark:bg-orange-950">
            <Flame className="h-4.5 w-4.5 text-orange-500" />
          </div>
          <h1 className="text-xl font-bold tracking-tight text-ink">Trending Stories</h1>
        </div>
        <p className="mb-4 text-sm text-ink-muted">
          Stories multiple sources are covering at once — clustering runs alongside every scrape.
        </p>

        <div className="mb-6 flex flex-wrap gap-2">
          {presets.map((p) => (
            <Button
              key={p.hours}
              size="sm"
              variant={hours === p.hours ? 'default' : 'outline'}
              onClick={() => setHours(p.hours)}
            >
              {p.label}
            </Button>
          ))}
        </div>

        {isLoading ? (
          <div className="space-y-3">
            <Skeleton className="h-24 w-full rounded-lg" />
            <Skeleton className="h-24 w-full rounded-lg" />
            <Skeleton className="h-24 w-full rounded-lg" />
          </div>
        ) : data && data.clusters.length > 0 ? (
          <div className="space-y-3">
            {data.clusters.map((cluster) => {
              const item = cluster.representative;
              const ref = parseContentRef(item.id);
              return (
                <div
                  key={item.id}
                  className="flex flex-wrap items-start justify-between gap-3 rounded-lg border border-border bg-card p-4"
                >
                  <div className="min-w-0 flex-1">
                    <span className="mb-2 inline-flex items-center gap-1 rounded-full bg-orange-100 px-2.5 py-0.5 text-xs font-medium text-orange-700 dark:bg-orange-950 dark:text-orange-300">
                      <Flame className="h-3 w-3" /> {cluster.memberCount} sources
                    </span>
                    <button
                      onClick={() => navigate(item.type === 'video' ? 'video-detail' : 'article-detail', { id: item.id })}
                      className="block text-left text-[15px] font-semibold leading-snug text-ink hover:text-primary"
                    >
                      {item.title}
                    </button>
                    <p className="mt-1 text-xs text-ink-muted">
                      {formatDistanceToNow(new Date(item.publishedAt), { addSuffix: true })}
                    </p>
                  </div>
                  <Button
                    variant="outline"
                    size="sm"
                    className="shrink-0"
                    onClick={() => ref && navigate('story-cluster', { type: item.type === 'video' ? 'video' : 'article', id: String(ref.contentId) })}
                  >
                    View all coverage <ArrowRight className="ml-1.5 h-3.5 w-3.5" />
                  </Button>
                </div>
              );
            })}
          </div>
        ) : (
          <EmptyState
            icon={Flame}
            title="No hot stories in this window"
            description="Try a wider time range above, or check back after the next scrape."
          />
        )}
      </motion.div>
    </div>
  );
}
