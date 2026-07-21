'use client';

import { FileText, Video, BookOpen, Mic, ArrowUpRight } from 'lucide-react';
import type { SourceReference } from '@/lib/types';

const SOURCE_TYPE_CONFIG: Record<
  SourceReference['sourceType'],
  { icon: typeof FileText; color: string }
> = {
  article: { icon: FileText, color: 'text-blue-600 dark:text-blue-400 bg-blue-50 dark:bg-blue-950' },
  video: { icon: Video, color: 'text-rose-600 dark:text-rose-400 bg-rose-50 dark:bg-rose-950' },
  summary: { icon: BookOpen, color: 'text-violet-600 dark:text-violet-400 bg-violet-50 dark:bg-violet-950' },
  transcript: { icon: Mic, color: 'text-amber-600 dark:text-amber-400 bg-amber-50 dark:bg-amber-950' },
};

interface SourceCardProps {
  source: SourceReference;
}

export default function SourceCard({ source }: SourceCardProps) {
  const config = SOURCE_TYPE_CONFIG[source.sourceType];
  const Icon = config.icon;

  return (
    <button
      onClick={() => source.url && window.open(source.url, '_blank', 'noopener,noreferrer')}
      className="group flex items-center gap-3 rounded-lg border border-border bg-card p-2.5 text-left transition-all duration-150 hover:border-primary/20 hover:shadow-sm"
    >
      {/* Thumbnail or icon */}
      {source.thumbnailUrl ? (
        <div className="h-10 w-10 shrink-0 overflow-hidden rounded-md bg-muted">
          <img
            src={source.thumbnailUrl}
            alt=""
            className="h-full w-full object-cover"
            loading="lazy"
          />
        </div>
      ) : (
        <div className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-md ${config.color}`}>
          <Icon className="h-4 w-4" />
        </div>
      )}

      {/* Content */}
      <div className="min-w-0 flex-1">
        <p className="truncate text-[13px] font-medium text-ink">
          {source.title}
        </p>
        <div className="flex items-center gap-1.5 text-[11px] text-ink-muted">
          <span>{source.source}</span>
          {source.time && (
            <>
              <span>·</span>
              <span>{source.time}</span>
            </>
          )}
        </div>
      </div>

      {/* Arrow */}
      <ArrowUpRight className="h-3.5 w-3.5 shrink-0 text-ink-muted opacity-0 transition-opacity duration-150 group-hover:opacity-100" />
    </button>
  );
}