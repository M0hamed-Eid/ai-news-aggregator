'use client';

import { useRef } from 'react';
import { Flame } from 'lucide-react';
import type { TrendingTopic } from '@/lib/types';

interface TrendingBarProps {
  items: TrendingTopic[];
  onSelect?: (item: TrendingTopic) => void;
}

export default function TrendingBar({ items, onSelect }: TrendingBarProps) {
  const scrollRef = useRef<HTMLDivElement>(null);

  return (
    <div className="relative">
      <div
        ref={scrollRef}
        className="flex gap-2 overflow-x-auto pb-2 scrollbar-none"
        style={{ scrollbarWidth: 'none' }}
      >
        {items.map((item) => (
          <button
            key={item.id}
            onClick={() => onSelect?.(item)}
            className="group flex shrink-0 items-center gap-1.5 rounded-full border border-border bg-surface px-3 py-1.5 text-sm font-medium text-ink transition-all duration-150 hover:border-primary/40 hover:bg-primary/5 hover:shadow-sm"
          >
            {item.isHotCluster && <Flame className="h-3.5 w-3.5 text-orange-500" />}
            <span>{item.label}</span>
            <span className="rounded-full bg-primary/10 px-1.5 py-0.5 text-[10px] font-semibold text-primary">
              {item.multiplier}x
            </span>
          </button>
        ))}
      </div>
      {/* Fade edges */}
      <div className="pointer-events-none absolute inset-y-0 left-0 w-8 bg-gradient-to-r from-background to-transparent" />
      <div className="pointer-events-none absolute inset-y-0 right-0 w-8 bg-gradient-to-l from-background to-transparent" />
    </div>
  );
}