'use client';

import { useState, useMemo, useEffect } from 'react';
import { useInfiniteQuery } from '@tanstack/react-query';
import { motion } from 'framer-motion';
import { Rss, Sparkles, Filter, X, Flame, ArrowRight } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { api, parseContentRef } from '@/lib/api';
import { useAppStore } from '@/lib/store';
import ArticleCard from '@/components/shared/ArticleCard';
import VideoCard from '@/components/shared/VideoCard';
import TrendingBar from '@/components/shared/TrendingBar';
import SkeletonCard from '@/components/shared/SkeletonCard';
import type { ContentItem, ContentCategory, TrendingTopic, Source } from '@/lib/types';

const GRADIENTS = [
  'from-indigo-600 via-violet-600 to-purple-500',
  'from-cyan-600 via-blue-600 to-indigo-500',
  'from-emerald-600 via-teal-600 to-cyan-500',
];

const ITEMS_PER_PAGE = 12;

// GET /api/news/home/[?before=...]'s real JSON shape (web/apps/news
// serializes items via the same serialize_item() used everywhere else, so
// ContentItem's fields line up exactly — see
// .claude/plans/effervescent-petting-nebula.md Phase 1). `hasMore`/`before`
// power real cursor-based pagination (M15 Phase 5) — trending/featured/
// sources/categories/topics only need to come from the FIRST page, since
// they describe the whole catalog rather than one page of it.
interface HotCluster {
  id: string;
  type: 'article' | 'video';
  title: string;
  memberCount: number;
}

interface HomeFeedResponse {
  items: ContentItem[];
  hasMore: boolean;
  featured: ContentItem[];
  trending: TrendingTopic[];
  hotClusters: HotCluster[];
  sources: Source[];
  categories: ContentCategory[];
  topics: string[];
}

export default function HomePage() {
  const { navigate, isLoggedIn, filterState, setFilter, clearFilters, hydrateContentState } = useAppStore();
  const [visibleCount, setVisibleCount] = useState(ITEMS_PER_PAGE);

  const { data, isLoading, isFetchingNextPage, hasNextPage, fetchNextPage } = useInfiniteQuery({
    queryKey: ['home-feed'],
    queryFn: ({ pageParam }) =>
      api.get<HomeFeedResponse>(pageParam ? `/api/news/home/?before=${encodeURIComponent(pageParam)}` : '/api/news/home/'),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (lastPage) => {
      if (!lastPage.hasMore || lastPage.items.length === 0) return undefined;
      return lastPage.items[lastPage.items.length - 1].publishedAt;
    },
  });

  const firstPage = data?.pages[0];

  const fetchedItems = useMemo(
    () => data?.pages.flatMap((page) => page.items) ?? [],
    [data]
  );

  useEffect(() => {
    if (fetchedItems.length) {
      hydrateContentState(fetchedItems);
    }
  }, [fetchedItems, hydrateContentState]);

  // Each page already arrives sorted newest-first and strictly older than
  // the previous page (the `before` cursor guarantees no overlap), so the
  // concatenation across pages is already sorted — this re-sort is cheap
  // insurance, not load-bearing.
  const allItems: ContentItem[] = useMemo(() => {
    return [...fetchedItems].sort(
      (a, b) => new Date(b.publishedAt).getTime() - new Date(a.publishedAt).getTime()
    );
  }, [fetchedItems]);

  const filteredItems = useMemo(() => {
    let items = allItems;
    const { search, category, source, topic, dateFrom } = filterState;

    if (search) {
      const q = search.toLowerCase();
      items = items.filter(item =>
        item.title.toLowerCase().includes(q) || item.summary.toLowerCase().includes(q)
      );
    }
    if (category !== 'all') {
      items = items.filter(item => item.category === category);
    }
    if (source !== 'all') {
      items = items.filter(item => item.source === source);
    }
    if (topic !== 'all') {
      items = items.filter(item => item.topics.includes(topic as any));
    }
    if (dateFrom) {
      items = items.filter(item => new Date(item.publishedAt) >= new Date(dateFrom));
    }

    return items;
  }, [allItems, filterState]);

  const hasActiveFilters = filterState.search || filterState.category !== 'all' || filterState.source !== 'all' || filterState.topic !== 'all' || filterState.dateFrom;

  // Reveal more of what's already been fetched first (instant, no network);
  // only reach for a real next page once the current batch is exhausted.
  const handleLoadMore = () => {
    if (visibleCount < filteredItems.length) {
      setVisibleCount(prev => prev + ITEMS_PER_PAGE);
    } else if (hasNextPage) {
      fetchNextPage().then(() => setVisibleCount(prev => prev + ITEMS_PER_PAGE));
    }
  };

  const visibleItems = filteredItems.slice(0, visibleCount);
  const canLoadMore = visibleCount < filteredItems.length || hasNextPage;

  return (
    <div className="mx-auto w-full max-w-[1450px] px-6 py-6 xl:px-8">
      {/* Hero */}
      <motion.div
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4 }}
        className="mb-8 text-center"
      >
        <h1 className="mb-2 text-3xl font-bold tracking-tight text-ink md:text-4xl">
          What&apos;s happening in AI
        </h1>
        <p className="text-base text-ink-muted">
          Your curated digest of the most important AI developments
        </p>
        <div className="mt-5 flex items-center justify-center gap-3">
          {isLoggedIn ? (
            <Button onClick={() => navigate('feed')} size="lg">
              <Rss className="mr-2 h-4 w-4" />
              Go to My Feed
            </Button>
          ) : (
            <>
              <Button onClick={() => navigate('signup')} size="lg">
                <Sparkles className="mr-2 h-4 w-4" />
                Get your personalized feed
              </Button>
              <Button variant="outline" size="lg" onClick={() => navigate('login')}>
                Log in
              </Button>
            </>
          )}
        </div>
      </motion.div>

      {/* Trending */}
      <motion.div
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4, delay: 0.1 }}
        className="mb-8"
      >
        <div className="mb-3 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Filter className="h-4 w-4 text-ink-muted" />
            <h2 className="text-sm font-semibold text-ink-muted uppercase tracking-wider">Trending</h2>
          </div>
          {isLoggedIn && (firstPage?.hotClusters?.length ?? 0) > 0 && (
            <button
              onClick={() => navigate('trending-stories')}
              className="flex items-center gap-1 text-xs font-medium text-orange-600 hover:underline dark:text-orange-400"
            >
              View all <ArrowRight className="h-3 w-3" />
            </button>
          )}
        </div>
        <TrendingBar
          items={firstPage?.trending ?? []}
          onSelect={(item) => {
            const [dimension, key] = item.id.split(':');
            if (dimension === 'entity') navigate('entity-profile', { id: key });
            else setFilter({ topic: item.label as any });
          }}
        />

        {/* Hot story clusters — restores the old home.html's SECOND
            trending mechanism (multiple sources covering the same story
            right now), distinct from the topic/entity pills above. Was
            missing entirely from the SPA's Home page until this fix. */}
        {(firstPage?.hotClusters?.length ?? 0) > 0 && (
          <div className="mt-2 flex flex-wrap gap-2">
            {firstPage!.hotClusters.map((hc) => {
              const ref = parseContentRef(hc.id);
              return (
                <button
                  key={hc.id}
                  onClick={() => ref && navigate('story-cluster', { type: hc.type, id: String(ref.contentId) })}
                  className="group flex items-center gap-1.5 rounded-full border border-orange-200 bg-orange-50 px-3 py-1.5 text-sm font-medium text-ink transition-all duration-150 hover:border-orange-300 hover:shadow-sm dark:border-orange-900 dark:bg-orange-950/40"
                >
                  <Flame className="h-3.5 w-3.5 text-orange-500" />
                  <span className="max-w-[220px] truncate">{hc.title}</span>
                  <span className="rounded-full bg-orange-100 px-1.5 py-0.5 text-[10px] font-semibold text-orange-700 dark:bg-orange-900 dark:text-orange-300">
                    {hc.memberCount} sources
                  </span>
                </button>
              );
            })}
          </div>
        )}

        {(firstPage?.trending?.length ?? 0) === 0 && (firstPage?.hotClusters?.length ?? 0) === 0 && (
          <p className="text-sm text-ink-muted">Nothing is trending right now — check back soon, burst detection runs alongside every scrape.</p>
        )}
      </motion.div>

      {/* Featured */}
      <motion.div
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4, delay: 0.15 }}
        className="mb-10"
      >
        <h2 className="mb-4 text-sm font-semibold text-ink-muted uppercase tracking-wider">Featured</h2>
        <div className="grid gap-4 md:grid-cols-3">
          {(firstPage?.featured ?? []).map((item, i) => (
            <button
              key={item.id}
              onClick={() => navigate(item.type === 'video' ? 'video-detail' : 'article-detail', { id: item.id })}
              className="group overflow-hidden rounded-xl border border-border bg-card text-left transition-all duration-200 hover:shadow-lg hover:-translate-y-1"
            >
              <div className={`h-36 bg-gradient-to-br ${GRADIENTS[i % GRADIENTS.length]} opacity-70`} />
              <div className="p-4">
                <div className="mb-2 flex items-center gap-1.5">
                  <span className="rounded-full bg-primary/10 px-2 py-0.5 text-[11px] font-medium text-primary">
                    {item.sourceLabel}
                  </span>
                </div>
                <h3 className="mb-1.5 line-clamp-2 text-sm font-semibold leading-snug text-ink group-hover:text-primary transition-colors">
                  {item.title}
                </h3>
                <p className="line-clamp-2 text-xs leading-relaxed text-ink-muted">{item.summary}</p>
              </div>
            </button>
          ))}
        </div>
      </motion.div>

      {/* Latest */}
      <motion.div
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4, delay: 0.2 }}
      >
        <h2 className="mb-4 text-sm font-semibold text-ink-muted uppercase tracking-wider">Latest</h2>

        {/* Filters */}
        <div className="mb-4 flex flex-wrap items-center gap-2 rounded-lg border border-border bg-card p-3">
          <div className="relative flex-1 min-w-[200px]">
            <Input
              placeholder="Filter articles..."
              value={filterState.search}
              onChange={(e) => setFilter({ search: e.target.value })}
              className="h-8 text-sm"
            />
          </div>
          <Select value={filterState.category} onValueChange={(v) => setFilter({ category: v as ContentCategory | 'all' })}>
            <SelectTrigger className="h-8 w-[160px] text-sm">
              <SelectValue placeholder="Category" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All categories</SelectItem>
              {(firstPage?.categories ?? []).map(cat => (
                <SelectItem key={cat} value={cat}>{cat}</SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Select value={filterState.source} onValueChange={(v) => setFilter({ source: v })}>
            <SelectTrigger className="h-8 w-[160px] text-sm">
              <SelectValue placeholder="Source" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All sources</SelectItem>
              {(firstPage?.sources ?? []).map(s => (
                <SelectItem key={s.key} value={s.key}>{s.name}</SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Select value={filterState.topic} onValueChange={(v) => setFilter({ topic: v as any })}>
            <SelectTrigger className="h-8 w-[180px] text-sm">
              <SelectValue placeholder="Topic" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All topics</SelectItem>
              {(firstPage?.topics ?? []).map(t => (
                <SelectItem key={t} value={t}>{t}</SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Input
            type="date"
            value={filterState.dateFrom}
            onChange={(e) => setFilter({ dateFrom: e.target.value })}
            className="h-8 w-[150px] text-sm"
          />
          {hasActiveFilters && (
            <Button variant="ghost" size="sm" onClick={clearFilters} className="h-8 text-xs">
              <X className="mr-1 h-3 w-3" /> Clear
            </Button>
          )}
        </div>

        {/* Results */}
        {isLoading ? (
          <div className="space-y-3">
            <SkeletonCard />
            <SkeletonCard />
            <SkeletonCard />
          </div>
        ) : (
          <>
            <div className="space-y-3">
              {visibleItems.map((item) => (
                item.type === 'video' ? (
                  <VideoCard key={item.id} item={item} />
                ) : (
                  <ArticleCard key={item.id} item={item} />
                )
              ))}
            </div>

            {isFetchingNextPage && (
              <div className="mt-4 space-y-3">
                <SkeletonCard />
                <SkeletonCard />
                <SkeletonCard />
              </div>
            )}

            {canLoadMore && (
              <div className="mt-6 flex justify-center">
                <Button variant="outline" onClick={handleLoadMore} disabled={isFetchingNextPage}>
                  {isFetchingNextPage ? 'Loading...' : 'Load more'}
                </Button>
              </div>
            )}

            {filteredItems.length === 0 && !hasActiveFilters && (
              <p className="py-8 text-center text-sm text-ink-muted">No items yet.</p>
            )}

            {filteredItems.length === 0 && hasActiveFilters && (
              <p className="py-8 text-center text-sm text-ink-muted">No items match your filters. Try clearing them.</p>
            )}
          </>
        )}
      </motion.div>
    </div>
  );
}