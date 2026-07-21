'use client';

import { formatDistanceToNow } from 'date-fns';
import { Bookmark, EyeOff, BookmarkCheck } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import type { ArticleItem, ContentCategory } from '@/lib/types';
import { useAppStore } from '@/lib/store';
import { parseContentRef } from '@/lib/api';
import { useImpressionTracking, trackClick } from '@/hooks/useBehaviorTracking';
import TopicBadge from './TopicBadge';
import DepthGauge from './DepthGauge';

const CATEGORY_COLORS: Record<ContentCategory, string> = {
  'Research': 'bg-violet-100 text-violet-700 dark:bg-violet-950 dark:text-violet-300',
  'Open Source': 'bg-green-100 text-green-700 dark:bg-green-950 dark:text-green-300',
  'Product / Model Databases': 'bg-blue-100 text-blue-700 dark:bg-blue-950 dark:text-blue-300',
  'Developer Communities': 'bg-orange-100 text-orange-700 dark:bg-orange-950 dark:text-orange-300',
  'Government': 'bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300',
  'Funding': 'bg-amber-100 text-amber-700 dark:bg-amber-950 dark:text-amber-300',
  'Media': 'bg-rose-100 text-rose-700 dark:bg-rose-950 dark:text-rose-300',
};

const CONTENT_TYPE_COLORS: Record<string, string> = {
  article: 'bg-surface text-ink-muted',
  release: 'bg-emerald-50 text-emerald-600 border border-emerald-200 dark:bg-emerald-950 dark:text-emerald-400 dark:border-emerald-800',
  paper: 'bg-violet-50 text-violet-600 border border-violet-200 dark:bg-violet-950 dark:text-violet-400 dark:border-violet-800',
};

interface ArticleCardProps {
  item: ArticleItem;
  showReason?: boolean;
}

export default function ArticleCard({ item, showReason = false }: ArticleCardProps) {
  const { navigate, toggleSave, toggleHide, isItemSaved, isItemHidden } = useAppStore();
  const saved = isItemSaved(item.id);
  const hidden = isItemHidden(item.id);
  const ref = parseContentRef(item.id);
  const impressionRef = useImpressionTracking(ref?.contentType ?? 'article', ref?.contentId ?? 0, ref !== null && !hidden);

  if (hidden) return null;

  // Real per-article photo (item.imageUrl) if the source ever supplies one,
  // else the source's own branded artwork (frontend/public/sources/{key}.png)
  // — restores web/apps/catalog/templatetags/source_display.py's
  // "source_artwork" filter, which the old Django card ALWAYS rendered one
  // or the other of. The Z.ai-authored ArticleCard never had an image slot
  // at all (unlike its own VideoCard, which at least had a gradient
  // placeholder) — every article card was pure text, a real regression
  // vs. the old app where every card had a real visual.
  const thumbnailSrc = item.imageUrl || `/sources/${item.source}.png`;

  return (
    <div ref={impressionRef} className="group flex items-start gap-3 rounded-lg border border-border bg-card p-4 transition-all duration-200 hover:shadow-md hover:-translate-y-[1px]">
      <button
        onClick={() => {
          if (ref) trackClick(ref.contentType, ref.contentId);
          navigate('article-detail', { id: item.id });
        }}
        className="relative shrink-0 overflow-hidden rounded-lg bg-muted"
        style={{ width: 160, height: 90 }}
      >
        {/* eslint-disable-next-line @next/next/no-img-element -- mixed
            external (real article photos) + local (source artwork) sources,
            not worth a next/image remote-pattern config for this. */}
        <img
          src={thumbnailSrc}
          alt=""
          loading="lazy"
          className="h-full w-full object-cover"
          onError={(e) => {
            if (!e.currentTarget.src.endsWith('_default.png')) {
              e.currentTarget.src = '/sources/_default.png';
            }
          }}
        />
      </button>
      <div className="min-w-0 flex-1">
        {/* Recommended reason */}
        {showReason && item.recommendedReason && (
          <p className="mb-1.5 text-xs text-primary/80 italic">{item.recommendedReason}</p>
        )}
        {/* Rank badge */}
        {item.rank && (
          <span className="mr-1.5 inline-flex h-5 w-5 items-center justify-center rounded-full bg-primary/10 text-[10px] font-bold text-primary">
            {item.rank}
          </span>
        )}
        {/* Source + category + content type */}
        <div className="mb-1.5 flex flex-wrap items-center gap-1.5">
          <Badge variant="secondary" className="text-[11px] font-medium px-2 py-0">
            {item.sourceLabel}
          </Badge>
          <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-[11px] font-medium ${CATEGORY_COLORS[item.category]}`}>
            {item.category}
          </span>
          {item.contentType && (
            <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-[11px] font-medium ${CONTENT_TYPE_COLORS[item.contentType]}`}>
              {item.contentType === 'paper' ? '📄 Paper' : item.contentType === 'release' ? '🚀 Release' : '📝 Article'}
            </span>
          )}
        </div>
        {/* Title */}
        <button
          onClick={() => {
            if (ref) trackClick(ref.contentType, ref.contentId);
            navigate('article-detail', { id: item.id });
          }}
          className="mb-1 text-left text-[15px] font-semibold leading-snug text-ink transition-colors duration-150 hover:text-primary"
        >
          {item.title}
        </button>
        {/* Summary */}
        <p className="mb-2 line-clamp-2 text-sm leading-relaxed text-ink-muted">
          {item.summary}
        </p>
        {/* Meta */}
        <div className="mb-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-ink-muted">
          {item.author && (
            <span className="font-medium text-ink">{item.author}</span>
          )}
          <span>{formatDistanceToNow(new Date(item.publishedAt), { addSuffix: true })}</span>
          {item.technicalDepth && <DepthGauge depth={item.technicalDepth} />}
        </div>
        {/* Topic chips */}
        <div className="flex flex-wrap gap-1.5">
          {item.topics.slice(0, 3).map((topic) => (
            <TopicBadge key={topic} label={topic} topic={topic} />
          ))}
        </div>
      </div>
      {/* Actions */}
      <div className="flex shrink-0 flex-col gap-1">
        <button
          onClick={() => toggleSave(item.id)}
          className="rounded-lg p-1.5 text-ink-muted transition-colors duration-150 hover:bg-primary/10 hover:text-primary"
          title={saved ? 'Unsave' : 'Save'}
        >
          {saved ? <BookmarkCheck className="h-4 w-4 text-primary" /> : <Bookmark className="h-4 w-4" />}
        </button>
        <button
          onClick={() => toggleHide(item.id)}
          className="rounded-lg p-1.5 text-ink-muted transition-colors duration-150 hover:bg-destructive/10 hover:text-destructive"
          title="Hide"
        >
          <EyeOff className="h-4 w-4" />
        </button>
      </div>
    </div>
  );
}