'use client';

import { motion } from 'framer-motion';
import { FileText, Video, Tag, Search, Globe } from 'lucide-react';
import type { AssistantContextType } from '@/lib/types';

const CONTEXT_CONFIG: Record<
  AssistantContextType['type'],
  { icon: typeof FileText; label: string; color: string; emoji: string }
> = {
  article: { icon: FileText, label: 'Article', color: 'text-blue-600 dark:text-blue-400', emoji: '\uD83D\uDCC4' },
  video: { icon: Video, label: 'Video', color: 'text-rose-600 dark:text-rose-400', emoji: '\uD83C\uDFAC' },
  topic: { icon: Tag, label: 'Topic', color: 'text-violet-600 dark:text-violet-400', emoji: '\uD83C\uDFF7\uFE0F' },
  search: { icon: Search, label: 'Search', color: 'text-amber-600 dark:text-amber-400', emoji: '\uD83D\uDD0D' },
  global: { icon: Globe, label: 'Knowledge Base', color: 'text-emerald-600 dark:text-emerald-400', emoji: '\uD83C\uDF0D' },
};

interface ContextIndicatorProps {
  context: AssistantContextType;
}

export default function ContextIndicator({ context }: ContextIndicatorProps) {
  const config = CONTEXT_CONFIG[context.type];
  const Icon = config.icon;

  const detailLabel =
    context.type === 'article'
      ? context.title
      : context.type === 'video'
        ? context.title
        : context.type === 'topic'
          ? context.label
          : context.type === 'search'
            ? context.query
            : 'Entire Knowledge Base';

  return (
    <motion.div
      initial={{ opacity: 0, y: -4 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.2 }}
      className="flex items-center gap-2 rounded-lg border border-border bg-muted/50 px-3 py-2 text-xs"
    >
      <span className="text-sm">{config.emoji}</span>
      <span className="font-medium text-ink">Current {config.label}</span>
      <span className="text-ink-muted">·</span>
      <span className="max-w-[200px] truncate text-ink-muted">{detailLabel}</span>
      <button
        className="ml-auto rounded-full p-0.5 text-ink-muted transition-colors hover:bg-muted hover:text-ink"
        title="Switch to global context"
      >
        <span className="text-[10px]">&times;</span>
      </button>
    </motion.div>
  );
}