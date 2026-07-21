'use client';

import { formatDistanceToNow } from 'date-fns';
import { Play, Bookmark, EyeOff, BookmarkCheck, ExternalLink } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import type { VideoItem } from '@/lib/types';
import { useAppStore } from '@/lib/store';
import { parseContentRef } from '@/lib/api';
import { useImpressionTracking, trackClick } from '@/hooks/useBehaviorTracking';
import TopicBadge from './TopicBadge';
import DepthGauge from './DepthGauge';

function formatDuration(seconds: number): string {
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = seconds % 60;
  if (h > 0) return `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
  return `${m}:${String(s).padStart(2, '0')}`;
}

const GRADIENTS = [
  'from-indigo-600 via-purple-600 to-pink-500',
  'from-cyan-600 via-blue-600 to-indigo-500',
  'from-emerald-600 via-teal-600 to-cyan-500',
  'from-orange-600 via-red-500 to-pink-500',
];

interface VideoCardProps {
  item: VideoItem;
  showReason?: boolean;
}

export default function VideoCard({ item, showReason = false }: VideoCardProps) {
  const { navigate, toggleSave, toggleHide, isItemSaved, isItemHidden } = useAppStore();
  const saved = isItemSaved(item.id);
  const hidden = isItemHidden(item.id);
  const contentRef = parseContentRef(item.id);
  const impressionRef = useImpressionTracking(contentRef?.contentType ?? 'youtube_video', contentRef?.contentId ?? 0, contentRef !== null && !hidden);

  if (hidden) return null;

  // item.id is now type-prefixed ("video-123", see serialize_item's
  // docstring) — index off the LAST character (the varying numeric suffix)
  // instead of the 2nd, which would collapse every video onto the same
  // gradient since they all now share the "video-" prefix.
  const gradientIdx = item.id.charCodeAt(item.id.length - 1) % GRADIENTS.length;

  const handleOpen = () => {
    if (contentRef) trackClick(contentRef.contentType, contentRef.contentId);
    navigate('video-detail', { id: item.id });
  };

  return (
    <div ref={impressionRef} className="group flex items-start gap-3 rounded-lg border border-border bg-card p-4 transition-all duration-200 hover:shadow-md hover:-translate-y-[1px]">
      {/* Thumbnail — the real YouTube thumbnail (item.thumbnailUrl, always
          a real https://i.ytimg.com/... URL, see web/apps/catalog/models.py's
          YoutubeVideo.thumbnail_url property), not the placeholder gradient
          Z.ai's mockup used before real video data existed. The gradient
          stays as the background layer so a rare broken-image load still
          looks intentional instead of a blank box. */}
      <button
        onClick={handleOpen}
        className="relative shrink-0 overflow-hidden rounded-lg"
        style={{ width: 160, height: 90 }}
      >
        <div className={`absolute inset-0 bg-gradient-to-br ${GRADIENTS[gradientIdx]} opacity-80`} />
        {item.thumbnailUrl && (
          // eslint-disable-next-line @next/next/no-img-element -- external
          // youtube.com host, not worth a next/image remote-pattern config
          // for a single always-external source.
          <img
            src={item.thumbnailUrl}
            alt=""
            loading="lazy"
            className="absolute inset-0 h-full w-full object-cover"
            onError={(e) => { e.currentTarget.style.display = 'none'; }}
          />
        )}
        <div className="absolute inset-0 flex items-center justify-center">
          <div className="flex h-10 w-10 items-center justify-center rounded-full bg-black/40 backdrop-blur-sm transition-transform duration-200 group-hover:scale-110">
            <Play className="h-5 w-5 text-white fill-white" />
          </div>
        </div>
        <span className="absolute bottom-1.5 right-1.5 rounded bg-black/70 px-1.5 py-0.5 text-[11px] font-medium text-white">
          {formatDuration(item.duration)}
        </span>
      </button>
      <div className="min-w-0 flex-1">
        {showReason && item.recommendedReason && (
          <p className="mb-1 text-xs text-primary/80 italic">{item.recommendedReason}</p>
        )}
        {item.rank && (
          <span className="mr-1.5 inline-flex h-5 w-5 items-center justify-center rounded-full bg-primary/10 text-[10px] font-bold text-primary">
            {item.rank}
          </span>
        )}
        <div className="mb-1.5 flex flex-wrap items-center gap-1.5">
          <Badge variant="secondary" className="text-[11px] font-medium px-2 py-0">
            📹 {item.channelName || 'YouTube'}
          </Badge>
          <Badge variant="outline" className="text-[11px] font-medium px-2 py-0">
            Video
          </Badge>
        </div>
        <button
          onClick={handleOpen}
          className="mb-1 text-left text-[15px] font-semibold leading-snug text-ink transition-colors duration-150 hover:text-primary"
        >
          {item.title}
        </button>
        <p className="mb-2 line-clamp-2 text-sm leading-relaxed text-ink-muted">
          {item.summary}
        </p>
        <div className="mb-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-ink-muted">
          {item.channelName && <span className="font-medium text-ink">{item.channelName}</span>}
          <span>{formatDistanceToNow(new Date(item.publishedAt), { addSuffix: true })}</span>
          {item.technicalDepth && <DepthGauge depth={item.technicalDepth} />}
        </div>
        <div className="flex flex-wrap gap-1.5">
          {item.topics.slice(0, 3).map((topic) => (
            <TopicBadge key={topic} label={topic} topic={topic} />
          ))}
        </div>
      </div>
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