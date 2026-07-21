'use client';

import { useState, useMemo, useEffect } from 'react';
import { useQuery } from '@tanstack/react-query';
import { motion } from 'framer-motion';
import { Search } from 'lucide-react';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { api } from '@/lib/api';
import { useAppStore } from '@/lib/store';
import ArticleCard from '@/components/shared/ArticleCard';
import VideoCard from '@/components/shared/VideoCard';
import EmptyState from '@/components/shared/EmptyState';
import SkeletonCard from '@/components/shared/SkeletonCard';
import type { ContentItem } from '@/lib/types';

const SUGGESTED = [
  'agentic coding tools', 'llm quantization techniques', 'RAG architecture',
  'AI safety alignment', 'multimodal models', 'open source LLMs',
];

const DEBOUNCE_MS = 300;

interface SearchResponse {
  items: ContentItem[];
  usedSemantic: boolean;
}

export default function SearchPage() {
  const { hydrateContentState } = useAppStore();
  const [query, setQuery] = useState('');
  const [debouncedQuery, setDebouncedQuery] = useState('');
  const [typeFilter, setTypeFilter] = useState<'all' | 'article' | 'video'>('all');

  // Debounce the real network call so semantic search doesn't fire on every
  // keystroke — see AI Compass Phase 1 plan (frontend/src/lib/api.ts's
  // GET /api/news/search/ is real pgvector search, not a substring filter).
  useEffect(() => {
    const timer = setTimeout(() => setDebouncedQuery(query.trim()), DEBOUNCE_MS);
    return () => clearTimeout(timer);
  }, [query]);

  const { data, isLoading, isFetching } = useQuery({
    queryKey: ['search', debouncedQuery],
    queryFn: () => api.get<SearchResponse>(`/api/news/search/?q=${encodeURIComponent(debouncedQuery)}`),
    enabled: debouncedQuery.length > 0,
  });

  useEffect(() => {
    if (data?.items) hydrateContentState(data.items);
  }, [data, hydrateContentState]);

  const results = useMemo(() => data?.items ?? [], [data]);

  const filtered = useMemo(() => {
    if (typeFilter === 'all') return results;
    return results.filter(item => item.type === typeFilter);
  }, [results, typeFilter]);

  // Covers both the debounce window (query already changed, fetch not fired
  // yet) and the in-flight fetch itself, so the skeleton never gaps.
  const isSearching = query.trim().length > 0 && (query.trim() !== debouncedQuery || isLoading || isFetching);

  return (
    <div className="mx-auto max-w-5xl px-4 py-8 md:px-6">
      <motion.div
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.3 }}
        className="mb-8 text-center"
      >
        <h1 className="mb-6 text-3xl font-bold tracking-tight text-ink md:text-4xl">
          Search AI news
        </h1>
        <div className="relative mx-auto max-w-3xl">
          <Search className="absolute left-4 top-1/2 h-5 w-5 -translate-y-1/2 text-ink-muted" />
          <Input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="agentic coding tools, llm quantization techniques..."
            className="h-12 pl-12 pr-4 text-base rounded-xl border-border bg-surface shadow-sm focus-visible:ring-primary"
            autoFocus
          />
        </div>
      </motion.div>

      {!query.trim() && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 0.2 }}
          className="text-center"
        >
          <p className="mb-4 text-sm text-ink-muted">Try searching for:</p>
          <div className="flex flex-wrap justify-center gap-2">
            {SUGGESTED.map(s => (
              <button
                key={s}
                onClick={() => setQuery(s)}
                className="rounded-full border border-border bg-surface px-3.5 py-1.5 text-sm text-ink-muted transition-all duration-150 hover:border-primary/40 hover:text-primary"
              >
                {s}
              </button>
            ))}
          </div>
        </motion.div>
      )}

      {query.trim() && (
        <>
          {isSearching ? (
            <div className="space-y-3">
              <SkeletonCard />
              <SkeletonCard />
              <SkeletonCard />
            </div>
          ) : (
            <>
              <div className="mb-4 flex items-center justify-between">
                <Tabs value={typeFilter} onValueChange={(v) => setTypeFilter(v as any)}>
                  <TabsList>
                    <TabsTrigger value="all">All ({results.length})</TabsTrigger>
                    <TabsTrigger value="article">Articles ({results.filter(i => i.type === 'article').length})</TabsTrigger>
                    <TabsTrigger value="video">Videos ({results.filter(i => i.type === 'video').length})</TabsTrigger>
                  </TabsList>
                </Tabs>
              </div>

              {filtered.length > 0 ? (
                <div className="space-y-3">
                  {filtered.map(item => (
                    item.type === 'video' ? (
                      <VideoCard key={item.id} item={item} />
                    ) : (
                      <ArticleCard key={item.id} item={item} />
                    )
                  ))}
                </div>
              ) : (
                <EmptyState
                  icon={Search}
                  title="No results found"
                  description={`No articles or videos match "${query}". Try a different search term.`}
                />
              )}
            </>
          )}
        </>
      )}
    </div>
  );
}