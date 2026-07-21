'use client';

import { useEffect } from 'react';
import { useQuery } from '@tanstack/react-query';
import { motion } from 'framer-motion';
import { ArrowLeft, Bookmark, BookmarkCheck, ExternalLink, Share2, Lightbulb, Flame } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Separator } from '@/components/ui/separator';
import { Skeleton } from '@/components/ui/skeleton';
import { formatDistanceToNow } from 'date-fns';
import { api, parseContentRef } from '@/lib/api';
import { useAppStore } from '@/lib/store';
import TopicBadge from '@/components/shared/TopicBadge';
import DepthGauge from '@/components/shared/DepthGauge';
import ArticleCard from '@/components/shared/ArticleCard';
import VideoCard from '@/components/shared/VideoCard';
import type { ArticleItem, ContentItem } from '@/lib/types';

const CATEGORY_COLORS: Record<string, string> = {
  'Research': 'bg-violet-100 text-violet-700 dark:bg-violet-950 dark:text-violet-300',
  'Open Source': 'bg-green-100 text-green-700 dark:bg-green-950 dark:text-green-300',
  'Product / Model Databases': 'bg-blue-100 text-blue-700 dark:bg-blue-950 dark:text-blue-300',
  'Developer Communities': 'bg-orange-100 text-orange-700 dark:bg-orange-950 dark:text-orange-300',
  'Government': 'bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300',
  'Funding': 'bg-amber-100 text-amber-700 dark:bg-amber-950 dark:text-amber-300',
  'Media': 'bg-rose-100 text-rose-700 dark:bg-rose-950 dark:text-rose-300',
};

// GET /api/news/articles/{id}/'s real JSON shape — every field matches
// ArticleItem exactly (web/apps/news/serializers.py::serialize_item), plus
// `related`: 0-4 full ContentItem objects (articles AND/or videos) from the
// same source.
interface ArticleDetailResponse extends ArticleItem {
  related: ContentItem[];
  clusterMemberCount: number;
}

export default function ArticleDetailPage() {
  const {
    pageParams,
    goBack,
    isItemSaved,
    toggleSave,
    navigate,
    hydrateContentState,
    setAssistantContext,
  } = useAppStore();
  const id = pageParams.id || '';
  const ref = parseContentRef(id);

  const { data: article, isLoading } = useQuery({
    queryKey: ['article-detail', id],
    queryFn: () => api.get<ArticleDetailResponse>(`/api/news/articles/${ref?.contentId}/`),
    enabled: ref !== null && ref.contentType === 'article',
    retry: false,
  });

  // Hydrate save/hide state for this article + its related items, and scope
  // the AI assistant panel to "this article" while it's open here. Resets to
  // global scope when the user navigates away (route change or unmount).
  useEffect(() => {
    if (!article) return;
    hydrateContentState([article, ...article.related]);
    setAssistantContext({ type: 'article', title: article.title, id: article.id });
    return () => setAssistantContext({ type: 'global' });
  }, [article, hydrateContentState, setAssistantContext]);

  const saved = isItemSaved(id);

  if (!ref || ref.contentType !== 'article') {
    return (
      <div className="mx-auto max-w-5xl px-4 py-16 text-center">
        <p className="text-ink-muted">Article not found.</p>
        <Button variant="link" onClick={goBack}>Go back</Button>
      </div>
    );
  }

  if (isLoading) {
    return (
      <div className="mx-auto max-w-6xl px-4 py-6 md:px-6">
        <div className="flex gap-8">
          <div className="min-w-0 flex-1 space-y-4">
            <Skeleton className="h-4 w-16" />
            <div className="flex gap-2">
              <Skeleton className="h-5 w-20 rounded-full" />
              <Skeleton className="h-5 w-28 rounded-full" />
            </div>
            <Skeleton className="h-8 w-3/4" />
            <Skeleton className="h-6 w-1/2" />
            <Skeleton className="h-4 w-32" />
            <Separator />
            <Skeleton className="h-4 w-full" />
            <Skeleton className="h-4 w-full" />
            <Skeleton className="h-4 w-2/3" />
          </div>
          <aside className="hidden w-48 shrink-0 space-y-3 lg:block">
            <Skeleton className="h-9 w-full" />
            <Skeleton className="h-9 w-full" />
            <Skeleton className="h-9 w-full" />
          </aside>
        </div>
      </div>
    );
  }

  if (!article) {
    return (
      <div className="mx-auto max-w-5xl px-4 py-16 text-center">
        <p className="text-ink-muted">Article not found.</p>
        <Button variant="link" onClick={goBack}>Go back</Button>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-6xl px-4 py-6 md:px-6">
      <div className="flex gap-8">
        {/* Main content */}
        <motion.div
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.3 }}
          className="min-w-0 flex-1"
        >
          {/* Back */}
          <button
            onClick={goBack}
            className="mb-4 flex items-center gap-1.5 text-sm text-ink-muted hover:text-ink transition-colors"
          >
            <ArrowLeft className="h-4 w-4" /> Back
          </button>

          {/* Meta row */}
          <div className="mb-3 flex flex-wrap items-center gap-2">
            <span className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${CATEGORY_COLORS[article.category] || ''}`}>
              {article.sourceLabel}
            </span>
            <span className="rounded-full bg-muted px-2.5 py-0.5 text-xs font-medium text-ink-muted">
              {article.category}
            </span>
            {article.contentType && (
              <Badge variant="outline" className="text-xs">
                {article.contentType === 'paper' ? '📄 Paper' : article.contentType === 'release' ? '🚀 Release' : '📝 Article'}
              </Badge>
            )}
            <span className="text-xs text-ink-muted">
              {formatDistanceToNow(new Date(article.publishedAt), { addSuffix: true })}
            </span>
          </div>

          {/* Title */}
          <h1 className="mb-4 text-2xl font-bold leading-tight tracking-tight text-ink md:text-3xl">
            {article.title}
          </h1>

          {/* Author */}
          {article.author && (
            <p className="mb-4 text-sm font-medium text-ink-muted">{article.author}</p>
          )}

          {/* Topics */}
          <div className="mb-6 flex flex-wrap gap-1.5">
            {article.topics.map(topic => (
              <TopicBadge key={topic} label={topic} topic={topic} />
            ))}
          </div>

          <Separator className="mb-6" />

          {/* Summary */}
          <div className="prose-compass mb-8">
            <p>{article.summary}</p>
          </div>

          {/* Why it matters */}
          {article.whyItMatters && (
            <div className="mb-8 rounded-xl border border-primary/20 bg-primary/5 p-5">
              <div className="mb-2 flex items-center gap-2">
                <Lightbulb className="h-4.5 w-4.5 text-primary" />
                <h3 className="text-sm font-semibold text-ink">Why it matters</h3>
              </div>
              <p className="text-sm leading-relaxed text-ink-muted">{article.whyItMatters}</p>
            </div>
          )}

          {/* Technical depth */}
          {article.technicalDepth && (
            <div className="mb-8 flex items-center gap-2">
              <span className="text-xs font-medium text-ink-muted">Technical depth:</span>
              <DepthGauge depth={article.technicalDepth} />
            </div>
          )}

          {/* Mentioned entities */}
          {article.mentionedEntities.length > 0 && (
            <div className="mb-8">
              <h3 className="mb-3 text-sm font-semibold text-ink">Mentioned:</h3>
              <div className="flex flex-wrap gap-1.5">
                {article.mentionedEntities.map(entity => (
                  <button
                    key={entity.id}
                    onClick={() => navigate('entity-profile', { id: entity.id })}
                    className="rounded-full border border-border bg-surface px-3 py-1 text-xs font-medium text-ink-muted transition-colors hover:border-primary/40 hover:text-primary"
                  >
                    {entity.name}
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Recommended */}
          {article.recommendedReason && (
            <div className="mb-8 rounded-lg bg-muted p-4">
              <p className="text-xs text-ink-muted italic">{article.recommendedReason}</p>
            </div>
          )}

          {/* Related from same source */}
          {article.related.length > 0 && (
            <div className="mb-8">
              <h3 className="mb-3 text-sm font-semibold text-ink uppercase tracking-wider">Related from {article.sourceLabel}</h3>
              <div className="space-y-3">
                {article.related.map(item => (
                  item.type === 'video' ? (
                    <VideoCard key={item.id} item={item} />
                  ) : (
                    <ArticleCard key={item.id} item={item} />
                  )
                ))}
              </div>
            </div>
          )}

          {/* Story cluster */}
          {article.clusterMemberCount > 1 && (
            <button
              onClick={() => navigate('story-cluster', { type: 'article', id: String(ref?.contentId ?? '') })}
              className="mb-8 flex w-full items-center justify-between rounded-lg border border-border bg-card p-4 text-left transition-colors hover:border-primary/30"
            >
              <span className="flex items-center gap-1.5 text-sm text-ink">
                <Flame className="h-4 w-4 text-orange-500" />
                Part of a story with {article.clusterMemberCount - 1} related item{article.clusterMemberCount - 1 === 1 ? '' : 's'}
              </span>
              <span className="text-sm font-semibold text-primary">View all coverage →</span>
            </button>
          )}
        </motion.div>

        {/* Sticky sidebar (desktop) */}
        <aside className="hidden w-48 shrink-0 lg:block">
          <div className="sticky top-20 space-y-3">
            <Button
              variant={saved ? 'secondary' : 'default'}
              className="w-full"
              onClick={() => toggleSave(id)}
            >
              {saved ? <BookmarkCheck className="mr-2 h-4 w-4" /> : <Bookmark className="mr-2 h-4 w-4" />}
              {saved ? 'Saved' : 'Save'}
            </Button>
            <Button variant="outline" className="w-full">
              <Share2 className="mr-2 h-4 w-4" /> Share
            </Button>
            <Button variant="outline" className="w-full" asChild>
              <a href={article.url} target="_blank" rel="noopener noreferrer">
                <ExternalLink className="mr-2 h-4 w-4" /> Read full article
              </a>
            </Button>
          </div>
        </aside>
      </div>

      {/* Mobile action bar */}
      <div className="fixed bottom-14 left-0 right-0 z-30 flex items-center justify-center gap-2 border-t border-border bg-surface/95 p-2 backdrop-blur-md lg:hidden">
        <Button size="sm" variant={saved ? 'secondary' : 'default'} onClick={() => toggleSave(id)}>
          {saved ? <BookmarkCheck className="mr-1.5 h-3.5 w-3.5" /> : <Bookmark className="mr-1.5 h-3.5 w-3.5" />}
          {saved ? 'Saved' : 'Save'}
        </Button>
        <Button size="sm" variant="outline" asChild>
          <a href={article.url} target="_blank" rel="noopener noreferrer">
            <ExternalLink className="mr-1.5 h-3.5 w-3.5" /> Read full
          </a>
        </Button>
      </div>
    </div>
  );
}
