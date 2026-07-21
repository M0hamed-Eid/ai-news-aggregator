'use client';

import type { TopicTag } from '@/lib/types';
import { Check } from 'lucide-react';
import { useAppStore } from '@/lib/store';

interface TopicBadgeProps {
  label: string;
  followed?: boolean;
  onToggle?: () => void;
  topic?: TopicTag;
}

export default function TopicBadge({ label, followed: followedProp, onToggle, topic }: TopicBadgeProps) {
  const { toggleFollowTopic, isTopicFollowed } = useAppStore();
  const isFollowed = followedProp !== undefined ? followedProp : topic ? isTopicFollowed(topic) : false;

  const handleClick = () => {
    if (topic && !onToggle) {
      toggleFollowTopic(topic);
    } else if (onToggle) {
      onToggle();
    }
  };

  return (
    <button
      onClick={handleClick}
      className={`
        inline-flex items-center gap-1 rounded-full px-3 py-1 text-xs font-medium transition-all duration-150
        ${isFollowed
          ? 'bg-primary text-primary-foreground hover:bg-primary/90'
          : 'border border-border bg-surface text-ink-muted hover:border-primary/40 hover:text-primary'
        }
      `}
    >
      {isFollowed && <Check className="h-3 w-3" />}
      {label}
    </button>
  );
}